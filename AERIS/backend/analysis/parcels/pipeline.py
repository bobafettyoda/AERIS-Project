from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from shapely import make_valid
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from analysis.common.geometry import repair_invalid_geometries
from analysis.common.io import atomic_write_json, file_sha256
from analysis.common.locking import file_lock
from analysis.common.geopackage import write_geopackage_atomic
from connectors.arcgis.client import (
    build_session,
    chunks,
    feature_collection_to_frame,
    object_ids_in_envelope,
    query_feature_batch,
    request_json,
    selected_fields,
)


MARYLAND_COUNTIES = {
    "001": "Allegany County",
    "003": "Anne Arundel County",
    "005": "Baltimore County",
    "009": "Calvert County",
    "011": "Caroline County",
    "013": "Carroll County",
    "015": "Cecil County",
    "017": "Charles County",
    "019": "Dorchester County",
    "021": "Frederick County",
    "023": "Garrett County",
    "025": "Harford County",
    "027": "Howard County",
    "029": "Kent County",
    "031": "Montgomery County",
    "033": "Prince George's County",
    "035": "Queen Anne's County",
    "037": "St. Mary's County",
    "039": "Somerset County",
    "041": "Talbot County",
    "043": "Washington County",
    "045": "Wicomico County",
    "047": "Worcester County",
    "510": "Baltimore City",
}


@dataclass(frozen=True)
class ParcelScope:
    scope_id: str
    scope_type: str
    label: str
    bbox_wgs84: tuple[
        float,
        float,
        float,
        float,
    ]
    geometry_wgs84: BaseGeometry
    zone_id: str | None = None
    zone_mode: str | None = None
    source_path: Path | None = None
    source_checksum: str | None = None


@dataclass(frozen=True)
class ParcelScopePaths:
    raw_directory: Path
    raw_snapshot: Path
    raw_metadata: Path
    page_directory: Path
    normalized_output: Path
    manifest_output: Path


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_config(
    config_path: Path,
) -> dict[str, Any]:
    value = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "Parcel configuration is not "
            "a YAML object."
        )

    return value


def resolve_path(
    project_directory: Path,
    relative_path: str,
) -> Path:
    return (
        project_directory
        / relative_path
    ).resolve()


def slugify(
    value: str,
) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.strip().lower(),
    ).strip("-")

    return normalized or "scope"


def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def json_hash(
    value: Any,
) -> str:
    return sha256_text(
        json.dumps(
            value,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            default=str,
        )
    )


def standardize_identifier(
    values: pd.Series,
    width: int | None = None,
) -> pd.Series:
    result = (
        values.astype("string")
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.strip()
    )

    if width is not None:
        result = result.str.zfill(
            width
        )

    return result


def column_name(
    frame: pd.DataFrame,
    *candidates: str,
) -> str | None:
    lookup = {
        str(column).casefold(): str(
            column
        )
        for column in frame.columns
    }

    for candidate in candidates:
        actual = lookup.get(
            candidate.casefold()
        )

        if actual is not None:
            return actual

    return None


def string_series(
    frame: pd.DataFrame,
    *candidates: str,
) -> pd.Series:
    actual = column_name(
        frame,
        *candidates,
    )

    if actual is None:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
        frame[actual]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def numeric_series(
    frame: pd.DataFrame,
    *candidates: str,
) -> pd.Series:
    result = pd.Series(
        np.nan,
        index=frame.index,
        dtype=float,
    )

    for candidate in candidates:
        actual = column_name(
            frame,
            candidate,
        )

        if actual is None:
            continue

        values = pd.to_numeric(
            frame[actual],
            errors="coerce",
        )

        result = result.where(
            result.notna(),
            values,
        )

    return result


def normalize_service_status(
    values: pd.Series,
) -> pd.Series:
    normalized = (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
    )

    yes_values = {
        "1",
        "true",
        "t",
        "yes",
        "y",
        "public",
        "available",
    }

    no_values = {
        "0",
        "false",
        "f",
        "no",
        "n",
        "none",
        "not available",
    }

    result = pd.Series(
        None,
        index=values.index,
        dtype="object",
    )

    result.loc[
        normalized.isin(
            yes_values
        )
    ] = "YES"

    result.loc[
        normalized.isin(
            no_values
        )
    ] = "NO"

    return result


def keyword_pattern(
    keywords: list[str],
) -> re.Pattern[str] | None:
    usable = [
        keyword.strip()
        for keyword in keywords
        if keyword.strip()
    ]
    if not usable:
        return None
    pattern = "|".join(
        re.escape(keyword)
        for keyword in sorted(
            usable,
            key=len,
            reverse=True,
        )
    )
    return re.compile(
        rf"(?<![A-Za-z0-9])(?:{pattern})(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )


def keyword_mask(
    values: pd.Series,
    keywords: list[str],
) -> pd.Series:
    pattern = keyword_pattern(keywords)
    if pattern is None:
        return pd.Series(
            False,
            index=values.index,
            dtype=bool,
        )
    return (
        values.astype("string")
        .fillna("")
        .str.contains(
            pattern,
            regex=True,
            na=False,
        )
    )


def keyword_evidence(
    values: pd.Series,
    keywords: list[str],
) -> pd.Series:
    pattern = keyword_pattern(keywords)
    if pattern is None:
        return pd.Series(
            "",
            index=values.index,
            dtype="string",
        )

    def matches(value: object) -> str:
        text = "" if value is None else str(value)
        found = {
            match.group(0).casefold()
            for match in pattern.finditer(text)
        }
        return "; ".join(sorted(found))

    return values.map(matches).astype("string")


def scope_from_bbox(
    *,
    west: float,
    south: float,
    east: float,
    north: float,
    scope_name: str | None = None,
) -> ParcelScope:
    if west >= east:
        raise ValueError(
            "west must be less than east."
        )

    if south >= north:
        raise ValueError(
            "south must be less than north."
        )

    if not (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
    ):
        raise ValueError(
            "Bounding box is outside "
            "valid WGS84 coordinates."
        )

    coordinates = (
        round(west, 7),
        round(south, 7),
        round(east, 7),
        round(north, 7),
    )

    digest = json_hash(
        coordinates
    )[:10]

    label = (
        scope_name.strip()
        if scope_name
        and scope_name.strip()
        else "Bounding-box parcel scope"
    )

    scope_id = (
        "bbox-"
        + slugify(label)
        + "-"
        + digest
    )

    return ParcelScope(
        scope_id=scope_id,
        scope_type="bbox",
        label=label,
        bbox_wgs84=coordinates,
        geometry_wgs84=box(
            *coordinates
        ),
    )


def scope_from_zone(
    *,
    config: dict[str, Any],
    project_directory: Path,
    zone_id: str,
) -> ParcelScope:
    requested_zone_id = (
        zone_id.strip()
    )

    if not requested_zone_id:
        raise ValueError(
            "zone_id cannot be empty."
        )

    for source in config[
        "inputs"
    ]["candidate_zones"]:
        path = resolve_path(
            project_directory,
            source["path"],
        )

        if not path.exists():
            continue

        layer = source.get(
            "layer"
        )

        if layer:
            frame = gpd.read_file(
                path,
                layer=layer,
            )
        else:
            frame = gpd.read_file(
                path
            )

        if "zone_id" not in frame:
            continue

        matches = frame.loc[
            frame["zone_id"]
            .astype(str)
            .eq(
                requested_zone_id
            )
        ]

        if matches.empty:
            continue

        if frame.crs is None:
            frame = frame.set_crs(
                "EPSG:4326"
            )

        matches = matches.to_crs(
            "EPSG:4326"
        )

        geometry = unary_union(
            list(
                matches.geometry
            )
        )

        if not geometry.is_valid:
            geometry = make_valid(
                geometry
            )

        if geometry.is_empty:
            raise RuntimeError(
                f"Candidate zone "
                f"{requested_zone_id!r} "
                "contains empty geometry."
            )

        west, south, east, north = (
            float(value)
            for value
            in geometry.bounds
        )

        return ParcelScope(
            scope_id=(
                "zone-"
                + slugify(
                    requested_zone_id
                )
            ),
            scope_type="candidate_zone",
            label=(
                "Candidate zone "
                + requested_zone_id
            ),
            bbox_wgs84=(
                west,
                south,
                east,
                north,
            ),
            geometry_wgs84=geometry,
            zone_id=(
                requested_zone_id
            ),
            zone_mode=str(
                source.get(
                    "mode",
                    "unknown",
                )
            ),
            source_path=path,
            source_checksum=(
                file_sha256(path)
            ),
        )

    raise KeyError(
        requested_zone_id
    )


def parcel_scope_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
    scope_id: str,
) -> ParcelScopePaths:
    outputs = config["outputs"]

    raw_root = resolve_path(
        project_directory,
        outputs[
            "raw_scope_directory"
        ]["path"],
    )

    cache_root = resolve_path(
        project_directory,
        outputs[
            "cache_directory"
        ]["path"],
    )

    derived_root = resolve_path(
        project_directory,
        outputs[
            "derived_scope_directory"
        ]["path"],
    )

    manifest_root = resolve_path(
        project_directory,
        outputs[
            "manifest_directory"
        ]["path"],
    )

    raw_directory = (
        raw_root / scope_id
    )

    return ParcelScopePaths(
        raw_directory=(
            raw_directory
        ),
        raw_snapshot=(
            raw_directory
            / "source_parcels.gpkg"
        ),
        raw_metadata=(
            raw_directory
            / "source_snapshot.json"
        ),
        page_directory=(
            cache_root
            / scope_id
            / "pages"
        ),
        normalized_output=(
            derived_root
            / f"{scope_id}.gpkg"
        ),
        manifest_output=(
            manifest_root
            / f"{scope_id}.json"
        ),
    )


def scope_geometry_in_crs(
    scope: ParcelScope,
    target_crs: str,
) -> BaseGeometry:
    return (
        gpd.GeoSeries(
            [
                scope.geometry_wgs84
            ],
            crs="EPSG:4326",
        )
        .to_crs(
            target_crs
        )
        .iloc[0]
    )


def read_json(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            f"Expected JSON object: {path}"
        )

    return value


def normalized_cache_is_current(
    *,
    paths: ParcelScopePaths,
    config_checksum: str,
    final_grid_checksum: str,
    scope: ParcelScope,
) -> bool:
    if not (
        paths.normalized_output.exists()
        and paths.manifest_output.exists()
    ):
        return False

    try:
        manifest = read_json(
            paths.manifest_output
        )
    except (
        json.JSONDecodeError,
        RuntimeError,
    ):
        return False

    return bool(
        manifest.get(
            "config_checksum"
        )
        == config_checksum
        and manifest.get(
            "final_grid_checksum"
        )
        == final_grid_checksum
        and manifest.get(
            "scope",
            {},
        ).get(
            "source_checksum"
        )
        == scope.source_checksum
    )


def download_source_snapshot(
    *,
    config: dict[str, Any],
    scope: ParcelScope,
    paths: ParcelScopePaths,
    refresh: bool,
) -> tuple[
    gpd.GeoDataFrame,
    dict[str, Any],
]:
    source = config["source"]

    layer_url = str(
        source["layer_url"]
    ).rstrip("/")

    target_crs = str(
        source["target_crs"]
    )

    raw_snapshot_fingerprint = json_hash(
        {
            "layer_url": layer_url,
            "target_crs": target_crs,
            "fields": list(source["fields"]),
            "scope_id": scope.scope_id,
            "scope_type": scope.scope_type,
            "bbox_wgs84": list(scope.bbox_wgs84),
            "scope_source_checksum": scope.source_checksum,
        }
    )

    if refresh:
        shutil.rmtree(
            paths.raw_directory,
            ignore_errors=True,
        )

        shutil.rmtree(
            paths.page_directory.parent,
            ignore_errors=True,
        )

    if (
        paths.raw_snapshot.exists()
        and paths.raw_metadata.exists()
        and not refresh
    ):
        metadata = read_json(paths.raw_metadata)
        if metadata.get("raw_snapshot_fingerprint") == raw_snapshot_fingerprint:
            print(
                (
                    "[Parcels] Using cached "
                    f"source snapshot for "
                    f"{scope.scope_id}"
                ),
                flush=True,
            )
            frame = gpd.read_file(
                paths.raw_snapshot,
                layer="source_parcels",
            )
            metadata["used_cached_snapshot"] = True
            return frame, metadata

        print(
            (
                "[Parcels] Cached raw snapshot fingerprint changed; "
                f"rebuilding {scope.scope_id}"
            ),
            flush=True,
        )
        shutil.rmtree(paths.raw_directory, ignore_errors=True)
        shutil.rmtree(paths.page_directory.parent, ignore_errors=True)

    paths.raw_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths.page_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    http = build_session()

    service_metadata = request_json(
        http,
        layer_url,
    )

    (
        object_id_field,
        output_fields,
    ) = selected_fields(
        service_metadata,
        source["fields"],
    )

    available_fields = {
        str(field["name"])
        for field
        in service_metadata.get(
            "fields",
            [],
        )
        if field.get("name")
    }

    missing_fields = sorted(
        set(source["fields"])
        - available_fields
    )

    west, south, east, north = (
        scope.bbox_wgs84
    )

    envelope = {
        "xmin": west,
        "ymin": south,
        "xmax": east,
        "ymax": north,
    }

    print(
        (
            "[Parcels] Requesting "
            f"ObjectIDs for {scope.label}"
        ),
        flush=True,
    )

    object_ids = (
        object_ids_in_envelope(
            session=http,
            layer_url=layer_url,
            envelope=envelope,
            where="1=1",
        )
    )

    source_object_count = len(
        object_ids
    )

    maximum_features = int(
        source[
            "maximum_scope_features"
        ]
    )

    if source_object_count > (
        maximum_features
    ):
        raise RuntimeError(
            (
                f"Parcel scope contains "
                f"{source_object_count:,} "
                "source features, exceeding "
                f"the configured maximum of "
                f"{maximum_features:,}. "
                "Use a smaller bounding box "
                "or candidate zone."
            )
        )

    page_size = min(
        int(source["page_size"]),
        int(
            service_metadata.get(
                "maxRecordCount",
                source[
                    "page_size"
                ],
            )
            or source["page_size"]
        ),
    )

    pages = chunks(
        object_ids,
        page_size,
    )

    all_features: list[
        dict[str, Any]
    ] = []

    reused_page_count = 0

    for page_number, page_ids in (
        enumerate(
            pages,
            start=1,
        )
    ):
        page_path = (
            paths.page_directory
            / (
                f"page_"
                f"{page_number:05d}"
                ".geojson"
            )
        )

        page_id_values = [int(value) for value in page_ids]
        payload = None
        if page_path.exists() and not refresh:
            candidate = json.loads(
                page_path.read_text(encoding="utf-8")
            )
            if candidate.get("_aeris_object_ids") == page_id_values:
                payload = candidate
                reused_page_count += 1

        if payload is None:
            features = (
                query_feature_batch(
                    session=http,
                    layer_url=layer_url,
                    object_ids=page_ids,
                    output_fields=(
                        output_fields
                    ),
                    name="parcels",
                )
            )

            payload = {
                "type": "FeatureCollection",
                "features": features,
                "_aeris_object_ids": page_id_values,
                "_aeris_raw_snapshot_fingerprint": raw_snapshot_fingerprint,
            }

            atomic_write_json(
                page_path,
                payload,
            )

        page_features = payload.get(
            "features",
            [],
        )

        all_features.extend(
            page_features
        )

        print(
            (
                f"[Parcels] Page "
                f"{page_number:,}/"
                f"{len(pages):,} | "
                f"{len(all_features):,}/"
                f"{source_object_count:,}"
            ),
            flush=True,
        )

    if len(all_features) != (
        source_object_count
    ):
        raise RuntimeError(
            (
                f"Requested "
                f"{source_object_count:,} "
                "parcel records but received "
                f"{len(all_features):,}."
            )
        )

    frame_wgs84 = (
        feature_collection_to_frame(
            all_features
        )
    )

    if (
        object_id_field
        not in frame_wgs84
    ):
        raise RuntimeError(
            "Parcel source response is "
            f"missing {object_id_field!r}."
        )

    frame_wgs84[
        "_source_object_id"
    ] = frame_wgs84[
        object_id_field
    ]

    frame = frame_wgs84.to_crs(
        target_crs
    )

    frame = repair_invalid_geometries(
        frame,
        name="parcels",
    )

    scope_geometry = (
        scope_geometry_in_crs(
            scope,
            target_crs,
        )
    )

    frame = frame.loc[
        frame.geometry.intersects(
            scope_geometry
        )
    ].copy()

    frame = frame.drop_duplicates(
        subset=[
            "_source_object_id",
        ]
    )

    if frame.empty:
        raise RuntimeError(
            "No parcel geometry remained "
            "after local scope filtering."
        )

    write_geopackage_atomic(
        path=paths.raw_snapshot,
        layers=[("source_parcels", frame)],
        indexes=[("source_parcels", "_source_object_id")],
    )

    metadata = {
        "schema_version": 1,
        "raw_snapshot_fingerprint": raw_snapshot_fingerprint,
        "retrieved_at_utc": (
            utc_now()
        ),
        "source_name": (
            source["name"]
        ),
        "layer_url": layer_url,
        "layer_name": (
            service_metadata.get(
                "name"
            )
        ),
        "object_id_field": (
            object_id_field
        ),
        "selected_fields": (
            output_fields
        ),
        "missing_requested_fields": (
            missing_fields
        ),
        "source_object_count": (
            source_object_count
        ),
        "snapshot_feature_count": (
            len(frame)
        ),
        "page_size": page_size,
        "page_count": len(pages),
        "reused_page_count": (
            reused_page_count
        ),
        "used_cached_snapshot": False,
        "raw_snapshot": str(
            paths.raw_snapshot
        ),
    }

    atomic_write_json(
        paths.raw_metadata,
        metadata,
    )

    metadata[
        "raw_snapshot_checksum"
    ] = file_sha256(
        paths.raw_snapshot
    )

    atomic_write_json(
        paths.raw_metadata,
        metadata,
    )

    return (
        frame,
        metadata,
    )


def normalize_parcels(
    *,
    source_frame: gpd.GeoDataFrame,
    config: dict[str, Any],
    scope: ParcelScope,
) -> gpd.GeoDataFrame:
    frame = source_frame.copy()

    normalization = config[
        "normalization"
    ]

    classification = config[
        "classification"
    ]

    square_meters_per_acre = float(
        normalization[
            "acreage_conversion"
        ][
            "square_meters_per_acre"
        ]
    )

    geometry_area_sq_m = (
        frame.geometry.area
    )

    geometry_area_acres = (
        geometry_area_sq_m
        / square_meters_per_acre
    )

    minimum_area_sq_m = float(
        normalization[
            "minimum_geometry_area_sq_m"
        ]
    )

    frame = frame.loc[
        geometry_area_sq_m.ge(
            minimum_area_sq_m
        )
    ].copy()

    geometry_area_sq_m = (
        frame.geometry.area
    )

    geometry_area_acres = (
        geometry_area_sq_m
        / square_meters_per_acre
    )

    source_object_id = (
        standardize_identifier(
            string_series(
                frame,
                "_source_object_id",
                "OBJECTID",
            )
        )
    )

    jurisdiction_code = (
        standardize_identifier(
            string_series(
                frame,
                "JURSCODE",
            )
        )
    )

    account_id = (
        standardize_identifier(
            string_series(
                frame,
                "ACCTID",
            )
        )
    )

    polygon_id = (
        standardize_identifier(
            string_series(
                frame,
                "POLYID",
            )
        )
    )

    base_parcel_id = pd.Series(
        "",
        index=frame.index,
        dtype="string",
    )

    account_available = (
        account_id.ne("")
    )

    base_parcel_id.loc[
        account_available
    ] = (
        jurisdiction_code.loc[
            account_available
        ].replace(
            "",
            "MD",
        )
        + "-"
        + account_id.loc[
            account_available
        ]
    )

    polygon_available = (
        base_parcel_id.eq("")
        & polygon_id.ne("")
    )

    base_parcel_id.loc[
        polygon_available
    ] = (
        "POLY-"
        + polygon_id.loc[
            polygon_available
        ]
    )

    object_available = (
        base_parcel_id.eq("")
        & source_object_id.ne("")
    )

    base_parcel_id.loc[
        object_available
    ] = (
        "OID-"
        + source_object_id.loc[
            object_available
        ]
    )

    duplicates = (
        base_parcel_id.duplicated(
            keep=False
        )
    )

    base_parcel_id.loc[
        duplicates
    ] = (
        base_parcel_id.loc[
            duplicates
        ]
        + "-OID-"
        + source_object_id.loc[
            duplicates
        ]
    )

    address = string_series(
        frame,
        "ADDRESS",
    )

    city = string_series(
        frame,
        "PREMCITY",
        "CITY",
    )

    zipcode = string_series(
        frame,
        "ZIPCODE",
    )

    property_address = (
        address
        + np.where(
            city.ne(""),
            ", " + city,
            "",
        )
        + np.where(
            zipcode.ne(""),
            " " + zipcode,
            "",
        )
    ).str.strip(
        " ,"
    )

    source_acres = numeric_series(
        frame,
        "POLYACRES",
        "ACRES",
    )

    source_acres = source_acres.where(
        source_acres.gt(0)
    )

    parcel_area_acres = (
        source_acres.where(
            source_acres.notna(),
            geometry_area_acres,
        )
    )

    land_use_code = (
        string_series(
            frame,
            "LU",
        )
    )

    land_use_description = (
        string_series(
            frame,
            "DESCLU",
        )
    )

    zoning_code = string_series(
        frame,
        "ZONING",
    )

    commercial_use = (
        string_series(
            frame,
            "DESCCIUSE",
            "CIUSE",
        )
    )

    exemption_description = (
        string_series(
            frame,
            "DESCEXCL",
            "EXCLASS",
        )
    )

    source_year_built = (
        numeric_series(
            frame,
            "YEARBLT",
        )
    )

    source_structure_sq_ft = (
        numeric_series(
            frame,
            "SQFTSTRC",
        )
    )

    source_building_units = (
        numeric_series(
            frame,
            "BLDG_UNITS",
        )
    )

    source_building_stories = (
        numeric_series(
            frame,
            "BLDG_STORY",
        )
    )

    appraised_land_value = (
        numeric_series(
            frame,
            "NFMLNDVL",
        )
    )

    appraised_improvement_value = (
        numeric_series(
            frame,
            "NFMIMPVL",
        )
    )

    appraised_total_value = (
        numeric_series(
            frame,
            "NFMTTLVL",
        )
    )

    classification_text = (
        exemption_description
        + " "
        + land_use_description
        + " "
        + commercial_use
    )

    public_land_flag = (
        keyword_mask(
            classification_text,
            list(
                classification[
                    "public_exemption_keywords"
                ]
            ),
        )
    )

    institutional_use_flag = (
        keyword_mask(
            classification_text,
            list(
                classification[
                    "institutional_keywords"
                ]
            ),
        )
    )

    public_classification_evidence = keyword_evidence(
        classification_text,
        list(
            classification[
                "public_exemption_keywords"
            ]
        ),
    )

    institutional_classification_evidence = keyword_evidence(
        classification_text,
        list(
            classification[
                "institutional_keywords"
            ]
        ),
    )

    existing_development_indicator = (
        source_year_built.fillna(
            0
        ).gt(0)
        | source_structure_sq_ft.fillna(
            0
        ).gt(0)
        | appraised_improvement_value.fillna(
            0
        ).gt(0)
    )

    core_data_missing = (
        base_parcel_id.eq("")
        | parcel_area_acres.isna()
    )

    availability_status = (
        np.select(
            [
                (
                    public_land_flag
                    | institutional_use_flag
                ),
                existing_development_indicator,
                core_data_missing,
            ],
            [
                "PUBLIC_OR_INSTITUTIONAL",
                "EXISTING_USE_REVIEW_REQUIRED",
                "DATA_INSUFFICIENT",
            ],
            default=(
                "POTENTIAL_FURTHER_REVIEW"
            ),
        )
    )

    availability_reason = (
        np.select(
            [
                (
                    public_land_flag
                    | institutional_use_flag
                ),
                existing_development_indicator,
                core_data_missing,
            ],
            [
                (
                    "Parcel attributes indicate "
                    "public or institutional use."
                ),
                (
                    "Parcel records indicate "
                    "existing improvements or "
                    "structures; availability "
                    "has not been established."
                ),
                (
                    "Core parcel identifier or "
                    "acreage information is "
                    "incomplete."
                ),
            ],
            default=(
                "No parcel-level attribute "
                "currently blocks further "
                "screening; ownership and "
                "availability remain unconfirmed."
            ),
        )
    )

    core_field_count = (
        base_parcel_id.ne("").astype(
            int
        )
        + parcel_area_acres.notna().astype(
            int
        )
        + (
            land_use_description.ne("")
            | zoning_code.ne("")
        ).astype(int)
        + property_address.ne("").astype(
            int
        )
    )

    parcel_data_confidence = (
        np.select(
            [
                core_field_count.ge(4),
                core_field_count.ge(2),
            ],
            [
                "HIGH",
                "MEDIUM",
            ],
            default="LOW",
        )
    )

    normalized = gpd.GeoDataFrame(
        {
            "parcel_id": (
                base_parcel_id
            ),
            "source_object_id": (
                source_object_id
            ),
            "jurisdiction_code": (
                jurisdiction_code
            ),
            "account_id": account_id,
            "polygon_id": polygon_id,
            "property_address": (
                property_address
            ),
            "parcel_area_acres": (
                parcel_area_acres.round(
                    6
                )
            ),
            "source_reported_acres": (
                source_acres.round(6)
            ),
            "geometry_area_acres": (
                geometry_area_acres.round(
                    6
                )
            ),
            "geometry_area_sq_m": (
                geometry_area_sq_m.round(
                    3
                )
            ),
            "land_use_code": (
                land_use_code
            ),
            "land_use_description": (
                land_use_description
            ),
            "zoning_code": zoning_code,
            "commercial_industrial_use": (
                commercial_use
            ),
            "exemption_description": (
                exemption_description
            ),
            "public_water_status": (
                normalize_service_status(
                    string_series(
                        frame,
                        "PFUW",
                    )
                )
            ),
            "public_sewer_status": (
                normalize_service_status(
                    string_series(
                        frame,
                        "PFUS",
                    )
                )
            ),
            "source_year_built": (
                source_year_built
            ),
            "source_structure_sq_ft": (
                source_structure_sq_ft
            ),
            "source_building_units": (
                source_building_units
            ),
            "source_building_stories": (
                source_building_stories
            ),
            "appraised_land_value": (
                appraised_land_value
            ),
            "appraised_improvement_value": (
                appraised_improvement_value
            ),
            "appraised_total_value": (
                appraised_total_value
            ),
            "public_land_flag": (
                public_land_flag
            ),
            "institutional_use_flag": (
                institutional_use_flag
            ),
            "public_classification_evidence": (
                public_classification_evidence
            ),
            "institutional_classification_evidence": (
                institutional_classification_evidence
            ),
            "existing_development_indicator": (
                existing_development_indicator
            ),
            "availability_status": (
                availability_status
            ),
            "availability_reason": (
                availability_reason
            ),
            "availability_confirmed": (
                False
            ),
            "parcel_data_confidence": (
                parcel_data_confidence
            ),
            "source_polygon_date": (
                string_series(
                    frame,
                    "POLYDATE",
                )
            ),
            "source_property_view_date": (
                string_series(
                    frame,
                    "MDPVDATE",
                )
            ),
            "source_assessment_date": (
                string_series(
                    frame,
                    "SDATDATE",
                )
            ),
            "source_zoning_change_date": (
                string_series(
                    frame,
                    "ZNCHGDAT",
                )
            ),
            "source_property_url": (
                string_series(
                    frame,
                    "SDATWEBADR",
                )
            ),
            "scope_id": (
                scope.scope_id
            ),
            "scope_type": (
                scope.scope_type
            ),
            "candidate_zone_id": (
                scope.zone_id
            ),
            "candidate_zone_mode": (
                scope.zone_mode
            ),
        },
        geometry=frame.geometry,
        crs=frame.crs,
    )

    minimum_acres = float(
        normalization[
            "minimum_parcel_acres"
        ]
    )

    normalized = normalized.loc[
        normalized[
            "geometry_area_acres"
        ].ge(minimum_acres)
    ].copy()

    if not normalized[
        "parcel_id"
    ].is_unique:
        raise RuntimeError(
            "Normalized parcel IDs are "
            "not unique."
        )

    return normalized


def add_scope_overlap(
    *,
    parcels: gpd.GeoDataFrame,
    scope: ParcelScope,
) -> gpd.GeoDataFrame:
    result = parcels.copy()

    scope_geometry = (
        scope_geometry_in_crs(
            scope,
            str(result.crs),
        )
    )

    intersection_area = (
        result.geometry
        .intersection(
            scope_geometry
        )
        .area
    )

    parcel_area = (
        result.geometry.area
    )

    result[
        "scope_overlap_area_sq_m"
    ] = intersection_area.round(3)

    square_meters_per_acre = (
        4046.8564224
    )

    result[
        "scope_overlap_area_acres"
    ] = (
        intersection_area
        / square_meters_per_acre
    ).round(6)

    result[
        "scope_overlap_fraction"
    ] = (
        intersection_area
        / parcel_area.replace(
            0,
            np.nan,
        )
    ).clip(
        lower=0,
        upper=1,
    ).round(6)

    return result


def add_statewide_context(
    *,
    parcels: gpd.GeoDataFrame,
    config: dict[str, Any],
    project_directory: Path,
) -> gpd.GeoDataFrame:
    final_grid_config = config[
        "inputs"
    ]["final_grid"]

    final_grid_path = resolve_path(
        project_directory,
        final_grid_config["path"],
    )

    if not final_grid_path.exists():
        raise RuntimeError(
            "Final statewide grid is "
            f"missing: {final_grid_path}"
        )

    grid = gpd.read_file(
        final_grid_path,
        layer=final_grid_config[
            "layer"
        ],
    ).to_crs(
        parcels.crs
    )

    requested_context_fields = [
        "cell_id",
        "technical_suitability_score",
        "effective_suitability_score",
        "equity_gate",
        "hard_excluded",
        "auto_screen_eligible",
        "exploration_screen_eligible",
        "county_fips",
        "county_name",
        "county",
        "GEOID",
    ]

    available_context_fields = [
        field
        for field
        in requested_context_fields
        if field in grid.columns
    ]

    context = grid[
        [
            *available_context_fields,
            "geometry",
        ]
    ].copy()

    rename_map = {
        "cell_id": (
            "statewide_cell_id"
        ),
        "technical_suitability_score": (
            "statewide_technical_score"
        ),
        "effective_suitability_score": (
            "statewide_effective_score"
        ),
        "equity_gate": (
            "statewide_equity_gate"
        ),
        "hard_excluded": (
            "statewide_hard_excluded"
        ),
        "auto_screen_eligible": (
            "statewide_auto_eligible"
        ),
        "exploration_screen_eligible": (
            "statewide_exploration_eligible"
        ),
        "county": (
            "_statewide_county_raw"
        ),
        "GEOID": (
            "statewide_tract_geoid"
        ),
    }

    context = context.rename(
        columns={
            source: target
            for source, target
            in rename_map.items()
            if source in context.columns
        }
    )

    # Keep only grid cells near the parcel scope.
    west, south, east, north = (
        parcels.total_bounds
    )

    context = context.cx[
        west:east,
        south:north,
    ].copy()

    if context.empty:
        raise RuntimeError(
            "No statewide grid cells intersect "
            "the parcel-scope bounding box."
        )

    parcel_shapes = parcels[
        [
            "parcel_id",
            "geometry",
        ]
    ].copy()

    parcel_shapes[
        "_parcel_index"
    ] = parcels.index

    # First preference: choose the statewide
    # grid cell having the largest polygon
    # overlap with each parcel.
    intersections = gpd.sjoin(
        parcel_shapes,
        context,
        how="left",
        predicate="intersects",
    )

    intersections[
        "_grid_overlap_area_sq_m"
    ] = np.nan

    has_grid = (
        intersections[
            "index_right"
        ].notna()
    )

    overlap_areas: list[float] = []

    for (
        parcel_geometry,
        grid_index,
    ) in zip(
        intersections.loc[
            has_grid,
            "geometry",
        ],
        intersections.loc[
            has_grid,
            "index_right",
        ],
        strict=True,
    ):
        grid_geometry = (
            context.geometry.loc[
                grid_index
            ]
        )

        overlap_areas.append(
            float(
                parcel_geometry
                .intersection(
                    grid_geometry
                )
                .area
            )
        )

    intersections.loc[
        has_grid,
        "_grid_overlap_area_sq_m",
    ] = overlap_areas

    best_overlap = (
        intersections.loc[
            has_grid
        ]
        .sort_values(
            [
                "_parcel_index",
                "_grid_overlap_area_sq_m",
            ],
            ascending=[
                True,
                False,
            ],
        )
        .drop_duplicates(
            subset=[
                "_parcel_index",
            ],
            keep="first",
        )
        .copy()
    )

    best_overlap[
        "statewide_context_distance_m"
    ] = 0.0

    best_overlap[
        "statewide_link_method"
    ] = (
        "maximum_grid_overlap"
    )

    matched_indices = set(
        best_overlap[
            "_parcel_index"
        ].tolist()
    )

    unmatched_indices = [
        index
        for index in parcels.index
        if index not in matched_indices
    ]

    # Rare fallback for unusual geometries
    # that do not intersect a land-grid cell.
    fallback = None

    if unmatched_indices:
        fallback_points = (
            gpd.GeoDataFrame(
                {
                    "_parcel_index": (
                        unmatched_indices
                    )
                },
                geometry=(
                    parcels.loc[
                        unmatched_indices,
                        "geometry",
                    ]
                    .representative_point()
                ),
                crs=parcels.crs,
            )
        )

        maximum_distance = float(
            config[
                "linkage"
            ][
                "maximum_grid_distance_m"
            ]
        )

        fallback = gpd.sjoin_nearest(
            fallback_points,
            context,
            how="left",
            max_distance=(
                maximum_distance
            ),
            distance_col=(
                "statewide_context_distance_m"
            ),
        )

        fallback = (
            fallback.sort_values(
                [
                    "_parcel_index",
                    "statewide_context_distance_m",
                ],
                na_position="last",
            )
            .drop_duplicates(
                subset=[
                    "_parcel_index",
                ],
                keep="first",
            )
        )

        fallback[
            "statewide_link_method"
        ] = (
            "nearest_representative_point_fallback"
        )

        fallback[
            "_grid_overlap_area_sq_m"
        ] = 0.0

    selected_frames = [
        best_overlap
    ]

    if fallback is not None:
        selected_frames.append(
            fallback
        )

    selected = pd.concat(
        selected_frames,
        ignore_index=True,
        sort=False,
    )

    attribute_columns = [
        column
        for column in selected.columns
        if column
        not in {
            "geometry",
            "index_right",
            "parcel_id",
        }
    ]

    attributes = selected[
        attribute_columns
    ].copy()

    result = parcels.copy()

    result[
        "_parcel_index"
    ] = result.index

    result = result.merge(
        attributes,
        how="left",
        on="_parcel_index",
        validate="one_to_one",
    )

    # Normalize county FIPS. Empty strings are
    # treated as missing rather than valid values.
    if "county_fips" in result:
        county_fips = (
            result[
                "county_fips"
            ]
            .astype("string")
            .str.strip()
            .replace(
                "",
                pd.NA,
            )
        )

    else:
        county_fips = pd.Series(
            pd.NA,
            index=result.index,
            dtype="string",
        )

    if (
        "_statewide_county_raw"
        in result.columns
    ):
        county_from_raw = (
            standardize_identifier(
                result[
                    "_statewide_county_raw"
                ],
                3,
            )
            .replace(
                "",
                pd.NA,
            )
        )

        county_fips = (
            county_fips.fillna(
                county_from_raw
            )
        )

    if (
        "statewide_tract_geoid"
        in result.columns
    ):
        county_from_geoid = (
            standardize_identifier(
                result[
                    "statewide_tract_geoid"
                ],
                11,
            )
            .str.slice(
                2,
                5,
            )
            .replace(
                "",
                pd.NA,
            )
        )

        county_fips = (
            county_fips.fillna(
                county_from_geoid
            )
        )

    result[
        "county_fips"
    ] = county_fips

    county_from_fips = (
        county_fips.map(
            MARYLAND_COUNTIES
        )
    )

    if "county_name" in result:
        county_name = (
            result[
                "county_name"
            ]
            .astype("string")
            .str.strip()
            .replace(
                "",
                pd.NA,
            )
        )

        result[
            "county_name"
        ] = county_name.fillna(
            county_from_fips
        )

    else:
        result[
            "county_name"
        ] = county_from_fips

    result[
        "statewide_context_complete"
    ] = result[
        "statewide_cell_id"
    ].notna()

    result = result.drop(
        columns=[
            "_parcel_index",
            "_statewide_county_raw",
        ],
        errors="ignore",
    )

    return gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=parcels.crs,
    )


def write_geopackage(
    frame: gpd.GeoDataFrame,
    path: Path,
    layer: str,
) -> None:
    write_geopackage_atomic(
        path=path,
        layers=[(layer, frame)],
        indexes=[(layer, "parcel_id")],
    )


def _build_parcel_scope_unlocked(
    *,
    config_path: Path,
    zone_id: str | None = None,
    bbox: tuple[
        float,
        float,
        float,
        float,
    ] | None = None,
    scope_name: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    started_at = time.monotonic()

    config_path = (
        config_path.resolve()
    )

    config = load_config(
        config_path
    )

    project_directory = (
        config_path.parents[2]
    )

    if (
        zone_id is None
        and bbox is None
    ):
        raise ValueError(
            "Provide either zone_id or bbox."
        )

    if (
        zone_id is not None
        and bbox is not None
    ):
        raise ValueError(
            "zone_id and bbox cannot "
            "be combined."
        )

    if zone_id is not None:
        scope = scope_from_zone(
            config=config,
            project_directory=(
                project_directory
            ),
            zone_id=zone_id,
        )

    else:
        assert bbox is not None

        scope = scope_from_bbox(
            west=float(bbox[0]),
            south=float(bbox[1]),
            east=float(bbox[2]),
            north=float(bbox[3]),
            scope_name=scope_name,
        )

    paths = parcel_scope_paths(
        config=config,
        project_directory=(
            project_directory
        ),
        scope_id=scope.scope_id,
    )

    final_grid_path = resolve_path(
        project_directory,
        config[
            "inputs"
        ]["final_grid"]["path"],
    )

    config_checksum = (
        file_sha256(
            config_path
        )
    )

    final_grid_checksum = (
        file_sha256(
            final_grid_path
        )
    )

    if (
        not refresh
        and normalized_cache_is_current(
            paths=paths,
            config_checksum=(
                config_checksum
            ),
            final_grid_checksum=(
                final_grid_checksum
            ),
            scope=scope,
        )
    ):
        print(
            (
                "[Parcels] Using current "
                f"normalized scope "
                f"{scope.scope_id}"
            ),
            flush=True,
        )

        return read_json(
            paths.manifest_output
        )

    print(
        (
            "[Parcels] Building scope "
            f"{scope.scope_id}"
        ),
        flush=True,
    )

    (
        source_frame,
        source_metadata,
    ) = download_source_snapshot(
        config=config,
        scope=scope,
        paths=paths,
        refresh=refresh,
    )

    normalized = normalize_parcels(
        source_frame=source_frame,
        config=config,
        scope=scope,
    )

    normalized = add_scope_overlap(
        parcels=normalized,
        scope=scope,
    )

    normalized = (
        add_statewide_context(
            parcels=normalized,
            config=config,
            project_directory=(
                project_directory
            ),
        )
    )

    write_geopackage(
        normalized,
        paths.normalized_output,
        "parcels",
    )

    availability_counts = {
        str(key): int(value)
        for key, value
        in normalized[
            "availability_status"
        ].value_counts(
            dropna=False
        ).items()
    }

    confidence_counts = {
        str(key): int(value)
        for key, value
        in normalized[
            "parcel_data_confidence"
        ].value_counts(
            dropna=False
        ).items()
    }

    county_counts = {
        str(key): int(value)
        for key, value
        in normalized[
            "county_name"
        ].astype("string")
        .fillna(
            "Unknown county"
        )
        .value_counts()
        .items()
    }

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "aeris_parcel_scope"
        ),
        "pipeline_version": (
            config[
                "pipeline_version"
            ]
        ),
        "generated_at_utc": (
            utc_now()
        ),
        "scope": {
            "scope_id": (
                scope.scope_id
            ),
            "scope_type": (
                scope.scope_type
            ),
            "label": scope.label,
            "bbox_wgs84": {
                "west": (
                    scope.bbox_wgs84[
                        0
                    ]
                ),
                "south": (
                    scope.bbox_wgs84[
                        1
                    ]
                ),
                "east": (
                    scope.bbox_wgs84[
                        2
                    ]
                ),
                "north": (
                    scope.bbox_wgs84[
                        3
                    ]
                ),
            },
            "zone_id": scope.zone_id,
            "zone_mode": (
                scope.zone_mode
            ),
            "source_path": (
                None
                if scope.source_path
                is None
                else str(
                    scope.source_path
                    .relative_to(
                        project_directory
                    )
                )
            ),
            "source_checksum": (
                scope.source_checksum
            ),
        },
        "source": (
            source_metadata
        ),
        "counts": {
            "normalized_parcels": (
                len(normalized)
            ),
            "statewide_context_complete": (
                int(
                    normalized[
                        "statewide_context_complete"
                    ].sum()
                )
            ),
            "public_land_flags": (
                int(
                    normalized[
                        "public_land_flag"
                    ].sum()
                )
            ),
            "institutional_use_flags": (
                int(
                    normalized[
                        "institutional_use_flag"
                    ].sum()
                )
            ),
            "existing_development_indicators": (
                int(
                    normalized[
                        "existing_development_indicator"
                    ].sum()
                )
            ),
        },
        "availability_status_counts": (
            availability_counts
        ),
        "confidence_counts": (
            confidence_counts
        ),
        "county_counts": county_counts,
        "area_statistics_acres": {
            "minimum": float(
                normalized[
                    "geometry_area_acres"
                ].min()
            ),
            "median": float(
                normalized[
                    "geometry_area_acres"
                ].median()
            ),
            "mean": float(
                normalized[
                    "geometry_area_acres"
                ].mean()
            ),
            "maximum": float(
                normalized[
                    "geometry_area_acres"
                ].max()
            ),
            "total": float(
                normalized[
                    "geometry_area_acres"
                ].sum()
            ),
        },
        "safeguards": {
            "availability_confirmed": (
                False
            ),
            "vacancy_inferred": False,
            "zoning_approval_inferred": (
                False
            ),
            "utility_capacity_inferred": (
                False
            ),
        },
        "config_checksum": (
            config_checksum
        ),
        "final_grid_checksum": (
            final_grid_checksum
        ),
        "outputs": {
            "raw_snapshot": str(
                paths.raw_snapshot
                .relative_to(
                    project_directory
                )
            ),
            "raw_metadata": str(
                paths.raw_metadata
                .relative_to(
                    project_directory
                )
            ),
            "normalized_parcels": str(
                paths.normalized_output
                .relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "raw_snapshot": (
                file_sha256(
                    paths.raw_snapshot
                )
            ),
            "normalized_parcels": (
                file_sha256(
                    paths.normalized_output
                )
            ),
        },
        "elapsed_seconds": round(
            time.monotonic()
            - started_at,
            3,
        ),
    }

    atomic_write_json(
        paths.manifest_output,
        manifest,
    )

    print(
        (
            "[Parcels] Complete | "
            f"{len(normalized):,} parcels | "
            f"{manifest['elapsed_seconds']:.1f}s"
        ),
        flush=True,
    )

    return manifest

def build_parcel_scope(
    *,
    config_path: Path,
    zone_id: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    scope_name: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    project_directory = config_path.parents[2]
    if zone_id is not None:
        scope = scope_from_zone(
            config=config,
            project_directory=project_directory,
            zone_id=zone_id,
        )
    elif bbox is not None:
        scope = scope_from_bbox(
            west=float(bbox[0]),
            south=float(bbox[1]),
            east=float(bbox[2]),
            north=float(bbox[3]),
            scope_name=scope_name,
        )
    else:
        raise ValueError("Provide either zone_id or bbox.")

    lock_path = (
        project_directory
        / "data"
        / "runtime"
        / "locks"
        / f"parcel-{scope.scope_id}.lock"
    )
    with file_lock(lock_path, timeout_seconds=1800):
        return _build_parcel_scope_unlocked(
            config_path=config_path,
            zone_id=zone_id,
            bbox=bbox,
            scope_name=scope_name,
            refresh=refresh,
        )
