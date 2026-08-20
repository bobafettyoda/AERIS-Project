from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from analysis.parcels.pipeline import (
    file_sha256,
    resolve_path,
)
from analysis.common.geometry import repair_invalid_geometries
from analysis.common.io import atomic_write_json
from analysis.common.geopackage import write_geopackage_atomic
from connectors.arcgis.client import (
    chunks,
    feature_collection_to_frame,
    query_feature_batch,
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_yaml(
    path: Path,
) -> dict[str, Any]:
    value = yaml.safe_load(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(value, dict):
        raise RuntimeError(
            f"Expected YAML object: {path}"
        )

    return value


def session(
    retry_count: int,
) -> requests.Session:
    retry = Retry(
        total=retry_count,
        connect=retry_count,
        read=retry_count,
        status=retry_count,
        backoff_factor=1.0,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=(
            "GET",
            "POST",
        ),
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    result = requests.Session()

    result.mount(
        "https://",
        adapter,
    )

    result.headers.update(
        {
            "User-Agent": (
                "AERIS/0.6 "
                "Maryland-planning-foundations"
            )
        }
    )

    return result


def request_json(
    http: requests.Session,
    url: str,
    *,
    data: dict[str, str] | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    if data is None:
        response = http.get(
            url,
            params={
                "f": "json",
            },
            timeout=timeout_seconds,
        )
    else:
        response = http.post(
            url,
            data=data,
            timeout=timeout_seconds,
        )

    response.raise_for_status()

    payload = response.json()

    if "error" in payload:
        raise RuntimeError(
            json.dumps(
                payload["error"],
                indent=2,
            )
        )

    return payload


def source_definitions(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[
        dict[str, Any]
    ] = []

    for group_name in (
        "political_boundaries",
        "priority_funding_areas",
        "critical_areas",
        "incentive_zones",
    ):
        group = config[
            "inputs"
        ][group_name]

        service_url = str(
            group[
                "service_url"
            ]
        ).rstrip("/")

        for source_id, layer in (
            group["layers"].items()
        ):
            results.append(
                {
                    "source_id": (
                        source_id
                    ),
                    "group": group_name,
                    "layer_url": (
                        f"{service_url}/"
                        f"{int(layer['id'])}"
                    ),
                    "output_layer": (
                        str(
                            layer[
                                "output_layer"
                            ]
                        )
                    ),
                }
            )

    return results


def all_object_ids(
    http: requests.Session,
    layer_url: str,
    timeout_seconds: int,
) -> list[int]:
    payload = request_json(
        http,
        f"{layer_url}/query",
        data={
            "where": "1=1",
            "returnIdsOnly": "true",
            "f": "json",
        },
        timeout_seconds=(
            timeout_seconds
        ),
    )

    result = [
        int(value)
        for value in (
            payload.get(
                "objectIds",
                [],
            )
            or []
        )
    ]

    result.sort()

    return result


def download_layer(
    *,
    http: requests.Session,
    source: dict[str, Any],
    target_crs: str,
    page_size: int,
    timeout_seconds: int,
) -> tuple[
    gpd.GeoDataFrame,
    dict[str, Any],
]:
    layer_url = source[
        "layer_url"
    ]

    metadata = request_json(
        http,
        layer_url,
        data=None,
        timeout_seconds=(
            timeout_seconds
        ),
    )

    object_id_field = (
        metadata.get(
            "objectIdField"
        )
        or metadata.get(
            "objectIdFieldName"
        )
    )

    if not object_id_field:
        raise RuntimeError(
            f"{source['source_id']}: "
            "object-ID field unavailable."
        )

    fields = [
        str(field["name"])
        for field
        in metadata.get(
            "fields",
            []
        )
        if field.get("name")
    ]

    ids = all_object_ids(
        http,
        layer_url,
        timeout_seconds,
    )

    maximum_page_size = int(
        metadata.get(
            "maxRecordCount",
            page_size,
        )
        or page_size
    )

    effective_page_size = min(
        page_size,
        maximum_page_size,
    )

    features: list[
        dict[str, Any]
    ] = []

    pages = chunks(
        ids,
        effective_page_size,
    )

    for page_number, page_ids in (
        enumerate(
            pages,
            start=1,
        )
    ):
        page_features = (
            query_feature_batch(
                session=http,
                layer_url=layer_url,
                object_ids=page_ids,
                output_fields=fields,
                name=source[
                    "source_id"
                ],
            )
        )

        features.extend(
            page_features
        )

        print(
            (
                "[Planning foundations] "
                f"{source['source_id']} "
                f"page {page_number:,}/"
                f"{len(pages):,} | "
                f"{len(features):,}/"
                f"{len(ids):,}"
            ),
            flush=True,
        )

    if len(features) != len(ids):
        raise RuntimeError(
            f"{source['source_id']}: "
            f"requested {len(ids):,} "
            f"records but received "
            f"{len(features):,}."
        )

    frame = feature_collection_to_frame(
        features
    )

    if frame.crs is None:
        frame = frame.set_crs(
            "EPSG:4326"
        )

    frame = frame.to_crs(
        target_crs
    )

    frame = repair_invalid_geometries(
        frame,
        name=source[
            "source_id"
        ],
    )

    return (
        frame,
        {
            "source_id": (
                source[
                    "source_id"
                ]
            ),
            "group": source["group"],
            "layer_url": layer_url,
            "layer_name": (
                metadata.get(
                    "name"
                )
            ),
            "geometry_type": (
                metadata.get(
                    "geometryType"
                )
            ),
            "object_id_field": (
                object_id_field
            ),
            "feature_count": (
                len(frame)
            ),
            "selected_fields": (
                fields
            ),
            "max_record_count": (
                metadata.get(
                    "maxRecordCount"
                )
            ),
            "editing_info": (
                metadata.get(
                    "editingInfo"
                )
            ),
        },
    )


def write_layers(
    path: Path,
    layers: list[tuple[str, gpd.GeoDataFrame]],
) -> list[str]:
    return write_geopackage_atomic(
        path=path,
        layers=layers,
    )


def acquire_foundations(
    *,
    config_path: Path,
    refresh: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()

    config_path = (
        config_path.resolve()
    )

    config = load_yaml(
        config_path
    )

    project_directory = (
        config_path.parents[2]
    )

    output_path = resolve_path(
        project_directory,
        config[
            "outputs"
        ][
            "statewide_foundations"
        ]["path"],
    )

    manifest_path = resolve_path(
        project_directory,
        config[
            "outputs"
        ][
            "statewide_manifest"
        ]["path"],
    )

    config_checksum = file_sha256(
        config_path
    )

    if (
        not refresh
        and output_path.exists()
        and manifest_path.exists()
    ):
        existing = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            existing.get(
                "config_checksum"
            )
            == config_checksum
        ):
            print(
                "[Planning foundations] "
                "Using current statewide snapshot",
                flush=True,
            )

            return existing

    if refresh:
        output_path.unlink(
            missing_ok=True
        )

        manifest_path.unlink(
            missing_ok=True
        )

    http = session(
        int(
            config[
                "analysis"
            ]["retry_count"]
        )
    )

    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    page_size = int(
        config[
            "analysis"
        ]["page_size"]
    )

    timeout_seconds = int(
        config[
            "analysis"
        ]["timeout_seconds"]
    )

    layers: list[
        tuple[
            str,
            gpd.GeoDataFrame,
        ]
    ] = []

    metadata: dict[
        str,
        Any,
    ] = {}

    for source in source_definitions(
        config
    ):
        print(
            (
                "[Planning foundations] "
                f"Downloading "
                f"{source['source_id']}"
            ),
            flush=True,
        )

        frame, source_metadata = (
            download_layer(
                http=http,
                source=source,
                target_crs=(
                    target_crs
                ),
                page_size=page_size,
                timeout_seconds=(
                    timeout_seconds
                ),
            )
        )

        layers.append(
            (
                source[
                    "output_layer"
                ],
                frame,
            )
        )

        metadata[
            source["source_id"]
        ] = source_metadata

    written_layers = write_layers(
        output_path,
        layers,
    )

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_planning_foundations"
        ),
        "pipeline_version": (
            config[
                "pipeline_version"
            ]
        ),
        "generated_at_utc": (
            utc_now()
        ),
        "snapshot_label": (
            config[
                "snapshot_label"
            ]
        ),
        "sources": metadata,
        "written_layers": (
            written_layers
        ),
        "config_checksum": (
            config_checksum
        ),
        "outputs": {
            "geopackage": str(
                output_path.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "geopackage": (
                file_sha256(
                    output_path
                )
            ),
        },
        "elapsed_seconds": round(
            time.monotonic()
            - started,
            3,
        ),
    }

    atomic_write_json(
        manifest_path,
        manifest,
    )

    print(
        (
            "[Planning foundations] Complete | "
            f"{len(written_layers)} layers | "
            f"{manifest['elapsed_seconds']:.1f}s"
        ),
        flush=True,
    )

    return manifest
