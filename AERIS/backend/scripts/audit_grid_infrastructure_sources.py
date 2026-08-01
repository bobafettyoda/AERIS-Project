from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
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


from app import config as app_config


REGIONS = {
    "western_maryland": {
        "xmin": -79.50,
        "ymin": 39.15,
        "xmax": -77.00,
        "ymax": 39.85,
    },
    "central_maryland": {
        "xmin": -77.50,
        "ymin": 38.55,
        "xmax": -76.35,
        "ymax": 39.75,
    },
    "eastern_maryland": {
        "xmin": -76.45,
        "ymin": 37.85,
        "xmax": -74.95,
        "ymax": 39.80,
    },
}


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def build_session() -> requests.Session:
    retries = Retry(
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
        max_retries=retries
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": (
                "AERIS/0.2 "
                "grid-infrastructure-audit"
            ),
        }
    )

    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    if data is None:
        response = session.get(
            url,
            params={
                "f": "json",
            },
            timeout=120,
        )
    else:
        response = session.post(
            url,
            data=data,
            timeout=120,
        )

    response.raise_for_status()

    payload = response.json()

    if "error" in payload:
        error = payload["error"]

        raise RuntimeError(
            f"{url}: "
            f"{error.get('code')} - "
            f"{error.get('message')}"
        )

    return payload


def query_count(
    session: requests.Session,
    layer_url: str,
    geometry: dict[str, float] | None = None,
) -> int:
    data = {
        "f": "json",
        "where": "1=1",
        "returnCountOnly": "true",
    }

    if geometry is not None:
        data.update(
            {
                "geometry": json.dumps(
                    {
                        **geometry,
                        "spatialReference": {
                            "wkid": 4326,
                        },
                    }
                ),
                "geometryType": (
                    "esriGeometryEnvelope"
                ),
                "inSR": "4326",
                "spatialRel": (
                    "esriSpatialRelIntersects"
                ),
            }
        )

    payload = request_json(
        session,
        f"{layer_url.rstrip('/')}/query",
        data=data,
    )

    return int(
        payload.get("count", 0)
    )


def extent_to_wgs84(
    extent: dict[str, Any] | None,
) -> dict[str, float] | None:
    if not extent:
        return None

    required = {
        "xmin",
        "ymin",
        "xmax",
        "ymax",
    }

    if not required.issubset(extent):
        return None

    spatial_reference = (
        extent.get(
            "spatialReference",
            {},
        )
    )

    wkid = (
        spatial_reference.get(
            "latestWkid"
        )
        or spatial_reference.get(
            "wkid"
        )
    )

    xmin = float(extent["xmin"])
    ymin = float(extent["ymin"])
    xmax = float(extent["xmax"])
    ymax = float(extent["ymax"])

    if wkid in {
        4326,
        4269,
    }:
        return {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
        }

    if wkid in {
        3857,
        102100,
        102113,
    }:
        transformer = (
            Transformer.from_crs(
                "EPSG:3857",
                "EPSG:4326",
                always_xy=True,
            )
        )

        west, south = (
            transformer.transform(
                xmin,
                ymin,
            )
        )

        east, north = (
            transformer.transform(
                xmax,
                ymax,
            )
        )

        return {
            "xmin": round(west, 6),
            "ymin": round(south, 6),
            "xmax": round(east, 6),
            "ymax": round(north, 6),
        }

    return None


def audit_layer(
    session: requests.Session,
    source_name: str,
    layer_url: str,
) -> dict[str, Any]:
    layer_url = layer_url.rstrip("/")

    print(
        f"[Audit] {source_name}",
        flush=True,
    )

    print(
        f"        {layer_url}",
        flush=True,
    )

    metadata = request_json(
        session,
        layer_url,
    )

    total_count = query_count(
        session,
        layer_url,
    )

    regional_counts = {}

    for region_name, envelope in (
        REGIONS.items()
    ):
        count = query_count(
            session,
            layer_url,
            geometry=envelope,
        )

        regional_counts[
            region_name
        ] = count

        print(
            (
                f"        {region_name}: "
                f"{count:,}"
            ),
            flush=True,
        )

    statewide_coverage_candidate = (
        total_count > 0
        and regional_counts[
            "western_maryland"
        ] > 0
        and regional_counts[
            "central_maryland"
        ] > 0
        and regional_counts[
            "eastern_maryland"
        ] > 0
    )

    result = {
        "source_name": source_name,
        "layer_url": layer_url,
        "layer_name": metadata.get(
            "name"
        ),
        "description": (
            metadata.get(
                "description"
            )
            or metadata.get(
                "serviceDescription"
            )
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
            metadata.get(
                "advancedQueryCapabilities",
                {},
            ).get(
                "supportsPagination"
            )
        ),
        "total_feature_count": (
            total_count
        ),
        "regional_feature_counts": (
            regional_counts
        ),
        "full_extent_wgs84": (
            extent_to_wgs84(
                metadata.get(
                    "extent"
                )
                or metadata.get(
                    "fullExtent"
                )
            )
        ),
        "statewide_coverage_candidate": (
            statewide_coverage_candidate
        ),
    }

    print(
        (
            "        total: "
            f"{total_count:,}"
        ),
        flush=True,
    )

    print(
        (
            "        statewide candidate: "
            f"{statewide_coverage_candidate}"
        ),
        flush=True,
    )

    return result


def main() -> None:
    required_constants = {
        "substations": (
            "SUBSTATIONS_LAYER_URL"
        ),
        "transmission_lines": (
            "TRANSMISSION_LINES_LAYER_URL"
        ),
    }

    missing_constants = [
        constant_name
        for constant_name
        in required_constants.values()
        if not hasattr(
            app_config,
            constant_name,
        )
    ]

    if missing_constants:
        raise RuntimeError(
            "Missing app.config constants: "
            + ", ".join(
                missing_constants
            )
        )

    source_urls = {
        source_name: str(
            getattr(
                app_config,
                constant_name,
            )
        )
        for source_name, constant_name
        in required_constants.items()
    }

    session = build_session()

    results = {}

    for source_name, layer_url in (
        source_urls.items()
    ):
        results[source_name] = (
            audit_layer(
                session=session,
                source_name=source_name,
                layer_url=layer_url,
            )
        )

    overall_statewide_candidate = all(
        result[
            "statewide_coverage_candidate"
        ]
        for result in results.values()
    )

    output = {
        "schema_version": 1,
        "audit": (
            "grid_infrastructure_sources"
        ),
        "generated_at_utc": utc_now(),
        "regions": REGIONS,
        "sources": results,
        "overall_statewide_candidate": (
            overall_statewide_candidate
        ),
        "decision": (
            "eligible_for_statewide_snapshot"
            if overall_statewide_candidate
            else (
                "replace_or_supplement_sources_"
                "before_statewide_scoring"
            )
        ),
    }

    output_path = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / (
            "grid_infrastructure_"
            "source_audit.json"
        )
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=== Infrastructure source audit ===")

    print(
        json.dumps(
            output,
            indent=2,
        )
    )

    print()
    print(
        "Audit manifest:",
        output_path,
    )

    if not overall_statewide_candidate:
        raise SystemExit(
            "SOURCE AUDIT FAILED: one or more "
            "layers do not demonstrate statewide "
            "Maryland coverage."
        )

    print()
    print("SOURCE AUDIT PASSED")


if __name__ == "__main__":
    main()
