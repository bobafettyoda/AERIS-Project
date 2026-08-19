from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[1]
)

PROJECT_DIRECTORY = (
    BACKEND_DIRECTORY.parent
)

if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIRECTORY),
    )


CONFIG_PATH = (
    PROJECT_DIRECTORY
    / "configs"
    / "parcels"
    / "maryland_parcels.yaml"
)


def session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
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
                "AERIS/0.3 parcel-audit"
            )
        }
    )

    return result


def request_json(
    http: requests.Session,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    if data is None:
        response = http.get(
            url,
            params={
                "f": "json",
            },
            timeout=120,
        )
    else:
        response = http.post(
            url,
            data=data,
            timeout=120,
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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the statewide Maryland "
            "parcel source in a scoped area."
        )
    )

    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=(
            "WEST",
            "SOUTH",
            "EAST",
            "NORTH",
        ),
        default=(
            -76.98,
            38.96,
            -76.90,
            39.03,
        ),
        help=(
            "WGS84 audit envelope. Default "
            "covers the College Park area."
        ),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    config = yaml.safe_load(
        CONFIG_PATH.read_text(
            encoding="utf-8"
        )
    )

    source = config["source"]

    layer_url = str(
        source["layer_url"]
    ).rstrip("/")

    http = session()

    metadata = request_json(
        http,
        layer_url,
    )

    available_fields = {
        str(field["name"])
        for field in metadata.get(
            "fields",
            []
        )
        if field.get("name")
    }

    requested_fields = list(
        source["fields"]
    )

    selected_fields = [
        field
        for field in requested_fields
        if field in available_fields
    ]

    missing_fields = sorted(
        set(requested_fields)
        - available_fields
    )

    west, south, east, north = (
        arguments.bbox
    )

    envelope = {
        "xmin": west,
        "ymin": south,
        "xmax": east,
        "ymax": north,
        "spatialReference": {
            "wkid": 4326,
        },
    }

    count_payload = request_json(
        http,
        f"{layer_url}/query",
        data={
            "where": "1=1",
            "geometry": json.dumps(
                envelope
            ),
            "geometryType": (
                "esriGeometryEnvelope"
            ),
            "inSR": "4326",
            "spatialRel": (
                "esriSpatialRelIntersects"
            ),
            "returnCountOnly": "true",
            "f": "json",
        },
    )

    id_payload = request_json(
        http,
        f"{layer_url}/query",
        data={
            "where": "1=1",
            "geometry": json.dumps(
                envelope
            ),
            "geometryType": (
                "esriGeometryEnvelope"
            ),
            "inSR": "4326",
            "spatialRel": (
                "esriSpatialRelIntersects"
            ),
            "returnIdsOnly": "true",
            "f": "json",
        },
    )

    object_ids = [
        int(value)
        for value in (
            id_payload.get(
                "objectIds",
                []
            )
            or []
        )
    ]

    object_ids.sort()

    sample_object_ids = (
        object_ids[:5]
    )

    if sample_object_ids:
        sample_payload = request_json(
            http,
            f"{layer_url}/query",
            data={
                "where": "1=1",
                "objectIds": ",".join(
                    str(value)
                    for value
                    in sample_object_ids
                ),
                "outFields": ",".join(
                    selected_fields
                ),
                "returnGeometry": "false",
                "f": "json",
            },
        )

    else:
        sample_payload = {
            "features": [],
        }

    advanced = metadata.get(
        "advancedQueryCapabilities",
        {},
    )

    audit = {
        "schema_version": 1,
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "source_name": source["name"],
        "layer_url": layer_url,
        "layer_name": metadata.get(
            "name"
        ),
        "geometry_type": metadata.get(
            "geometryType"
        ),
        "object_id_field": (
            metadata.get(
                "objectIdField"
            )
            or metadata.get(
                "objectIdFieldName"
            )
        ),
        "max_record_count": (
            metadata.get(
                "maxRecordCount"
            )
        ),
        "supports_pagination": (
            advanced.get(
                "supportsPagination"
            )
        ),
        "supports_geojson": (
            "geoJSON"
            in metadata.get(
                "supportedQueryFormats",
                ""
            )
        ),
        "requested_fields": (
            requested_fields
        ),
        "selected_fields": (
            selected_fields
        ),
        "missing_fields": (
            missing_fields
        ),
        "audit_bbox_wgs84": {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        },
        "matching_parcel_count": int(
            count_payload.get(
                "count",
                0,
            )
        ),
        "sample_records": (
            sample_payload.get(
                "features",
                []
            )
        ),
        "eligible_for_scoped_acquisition": (
            metadata.get(
                "geometryType"
            )
            == "esriGeometryPolygon"
            and bool(
                advanced.get(
                    "supportsPagination"
                )
            )
            and int(
                count_payload.get(
                    "count",
                    0,
                )
            )
            > 0
        ),
    }

    output_path = (
        PROJECT_DIRECTORY
        / config["outputs"][
            "audit_manifest"
        ]
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            audit,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            audit,
            indent=2,
        )
    )

    if not audit[
        "eligible_for_scoped_acquisition"
    ]:
        raise SystemExit(
            "PARCEL SOURCE AUDIT FAILED"
        )

    print()
    print(
        "PARCEL SOURCE AUDIT PASSED"
    )


if __name__ == "__main__":
    main()
