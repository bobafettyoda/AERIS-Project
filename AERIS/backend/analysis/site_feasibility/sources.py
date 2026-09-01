from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import geopandas as gpd
import requests

from analysis.common.geometry import repair_invalid_geometries
from analysis.common.io import atomic_write_json, read_json
from connectors.arcgis.client import (
    build_session,
    feature_collection_to_frame,
    query_feature_batch,
    request_json,
    selected_fields,
)


@dataclass(frozen=True)
class ScopedSourceResult:
    source_id: str
    frame: gpd.GeoDataFrame
    metadata: dict[str, Any]


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def empty_geodataframe(*, crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"geometry": []},
        geometry="geometry",
        crs=crs,
    )


def geometry_envelope_wgs84(
    geometry,
    *,
    source_crs: str,
) -> dict[str, float]:
    projected = gpd.GeoSeries(
        [geometry],
        crs=source_crs,
    ).to_crs("EPSG:4326")
    west, south, east, north = (
        float(value)
        for value in projected.iloc[0].bounds
    )
    return {
        "xmin": west,
        "ymin": south,
        "xmax": east,
        "ymax": north,
    }


def object_ids_allow_empty(
    session: requests.Session,
    *,
    layer_url: str,
    envelope_wgs84: dict[str, float],
    where: str = "1=1",
    timeout_seconds: int = 180,
) -> list[int]:
    payload = request_json(
        session,
        f"{layer_url.rstrip('/')}/query",
        data={
            "where": where,
            "returnIdsOnly": "true",
            "geometry": json.dumps(
                {
                    **envelope_wgs84,
                    "spatialReference": {"wkid": 4326},
                }
            ),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
        },
        timeout_seconds=timeout_seconds,
    )
    return sorted(
        int(value)
        for value in (payload.get("objectIds") or [])
    )


def _cache_is_current(
    *,
    metadata_path: Path,
    snapshot_path: Path,
    fingerprint: str,
) -> bool:
    if not metadata_path.exists():
        return False
    try:
        metadata = read_json(metadata_path)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return False
    if metadata.get("fingerprint") != fingerprint:
        return False
    if bool(metadata.get("empty", False)):
        return True
    return snapshot_path.exists()


def download_scoped_layer(
    *,
    source_id: str,
    layer_url: str,
    desired_fields: Sequence[str],
    scope_geometry,
    scope_crs: str,
    target_crs: str,
    cache_root: Path,
    page_size: int,
    timeout_seconds: int,
    where: str = "1=1",
    refresh: bool = False,
    maximum_features: int | None = None,
    user_agent: str = "AERIS/0.7 site-feasibility",
) -> ScopedSourceResult:
    layer_url = layer_url.rstrip("/")
    source_directory = cache_root / source_id
    page_directory = source_directory / "pages"
    snapshot_path = source_directory / "snapshot.gpkg"
    metadata_path = source_directory / "snapshot.json"

    envelope_wgs84 = geometry_envelope_wgs84(
        scope_geometry,
        source_crs=scope_crs,
    )
    fingerprint = stable_hash(
        {
            "source_id": source_id,
            "layer_url": layer_url,
            "desired_fields": list(desired_fields),
            "envelope_wgs84": envelope_wgs84,
            "where": where,
            "target_crs": target_crs,
        }
    )

    if refresh:
        shutil.rmtree(source_directory, ignore_errors=True)

    if _cache_is_current(
        metadata_path=metadata_path,
        snapshot_path=snapshot_path,
        fingerprint=fingerprint,
    ):
        metadata = read_json(metadata_path)
        frame = (
            empty_geodataframe(crs=target_crs)
            if bool(metadata.get("empty", False))
            else gpd.read_file(
                snapshot_path,
                layer="features",
            )
        )
        metadata["used_cache"] = True
        return ScopedSourceResult(
            source_id=source_id,
            frame=frame,
            metadata=metadata,
        )

    session = build_session(
        user_agent=user_agent,
        retry_count=6,
    )
    metadata = request_json(
        session,
        layer_url,
        timeout_seconds=timeout_seconds,
    )
    object_id_field, output_fields = selected_fields(
        metadata,
        desired_fields,
    )
    object_ids = object_ids_allow_empty(
        session,
        layer_url=layer_url,
        envelope_wgs84=envelope_wgs84,
        where=where,
        timeout_seconds=timeout_seconds,
    )

    if (
        maximum_features is not None
        and len(object_ids) > maximum_features
    ):
        raise RuntimeError(
            f"{source_id}: scoped query returned "
            f"{len(object_ids):,} features, exceeding "
            f"the configured maximum of {maximum_features:,}."
        )

    source_directory.mkdir(parents=True, exist_ok=True)
    page_directory.mkdir(parents=True, exist_ok=True)

    if not object_ids:
        frame = empty_geodataframe(crs=target_crs)
        # GeoPackage writers cannot create a layer with only an empty geometry
        # column reliably, so cache only metadata for an empty source.
        snapshot_path.unlink(missing_ok=True)
        source_metadata = {
            "fingerprint": fingerprint,
            "source_id": source_id,
            "layer_url": layer_url,
            "layer_name": metadata.get("name"),
            "geometry_type": metadata.get("geometryType"),
            "object_id_field": object_id_field,
            "selected_fields": output_fields,
            "source_object_count": 0,
            "snapshot_feature_count": 0,
            "page_count": 0,
            "used_cache": False,
            "empty": True,
        }
        atomic_write_json(metadata_path, source_metadata)
        return ScopedSourceResult(
            source_id=source_id,
            frame=frame,
            metadata=source_metadata,
        )

    effective_page_size = min(
        int(page_size),
        int(metadata.get("maxRecordCount") or page_size),
    )
    pages = [
        object_ids[start : start + effective_page_size]
        for start in range(0, len(object_ids), effective_page_size)
    ]
    features: list[dict[str, Any]] = []
    reused_pages = 0

    for page_number, page_ids in enumerate(pages, start=1):
        page_path = page_directory / f"page_{page_number:05d}.json"
        page_fingerprint = stable_hash(
            {
                "fingerprint": fingerprint,
                "object_ids": page_ids,
            }
        )
        page_payload: dict[str, Any] | None = None
        if page_path.exists() and not refresh:
            try:
                candidate = read_json(page_path)
                if (
                    candidate.get("fingerprint") == page_fingerprint
                    and candidate.get("object_ids") == page_ids
                ):
                    page_payload = candidate
                    reused_pages += 1
            except (OSError, json.JSONDecodeError, RuntimeError):
                page_payload = None

        if page_payload is None:
            page_features = query_feature_batch(
                session=session,
                layer_url=layer_url,
                object_ids=page_ids,
                output_fields=output_fields,
                name=source_id,
            )
            page_payload = {
                "fingerprint": page_fingerprint,
                "object_ids": page_ids,
                "features": page_features,
            }
            atomic_write_json(page_path, page_payload)

        features.extend(page_payload.get("features", []))
        print(
            f"      [{source_id}] page {page_number:,}/{len(pages):,} | "
            f"{len(features):,}/{len(object_ids):,}",
            flush=True,
        )

    if len(features) != len(object_ids):
        raise RuntimeError(
            f"{source_id}: requested {len(object_ids):,} records but "
            f"received {len(features):,}."
        )

    frame = feature_collection_to_frame(features).to_crs(target_crs)
    frame = repair_invalid_geometries(
        frame,
        name=source_id,
    )
    frame = frame.loc[
        frame.geometry.intersects(scope_geometry)
    ].copy()
    if object_id_field in frame.columns:
        frame = frame.drop_duplicates(
            subset=[object_id_field],
            keep="first",
        )

    if snapshot_path.exists():
        snapshot_path.unlink()
    if not frame.empty:
        frame.to_file(
            snapshot_path,
            layer="features",
            driver="GPKG",
            index=False,
        )

    source_metadata = {
        "fingerprint": fingerprint,
        "source_id": source_id,
        "layer_url": layer_url,
        "layer_name": metadata.get("name"),
        "geometry_type": metadata.get("geometryType"),
        "object_id_field": object_id_field,
        "selected_fields": output_fields,
        "source_object_count": len(object_ids),
        "snapshot_feature_count": len(frame),
        "page_count": len(pages),
        "reused_page_count": reused_pages,
        "used_cache": False,
        "empty": frame.empty,
    }
    atomic_write_json(metadata_path, source_metadata)

    return ScopedSourceResult(
        source_id=source_id,
        frame=frame,
        metadata=source_metadata,
    )
