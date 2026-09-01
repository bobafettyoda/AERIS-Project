from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.common.io import atomic_write_json, load_yaml
from connectors.arcgis.client import ArcGISClient


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent


def layer_audit(client: ArcGISClient, url: str) -> dict[str, Any]:
    metadata = client.metadata(url)
    return {
        "url": url,
        "name": metadata.get("name"),
        "geometry_type": metadata.get("geometryType"),
        "object_id_field": (
            metadata.get("objectIdField")
            or metadata.get("objectIdFieldName")
        ),
        "max_record_count": metadata.get("maxRecordCount"),
        "supports_pagination": metadata.get(
            "advancedQueryCapabilities", {}
        ).get("supportsPagination"),
        "available": True,
    }


def main() -> None:
    config = load_yaml(
        PROJECT_DIRECTORY
        / "configs"
        / "parcels"
        / "site_feasibility.yaml"
    )
    client = ArcGISClient.create(
        user_agent="AERIS/0.7 site-source-audit",
        retry_count=5,
        timeout_seconds=120,
    )
    sources: dict[str, Any] = {}
    terrain_url = str(config["inputs"]["terrain"]["image_server_url"])
    terrain_metadata = client.metadata(terrain_url)
    sources["terrain"] = {
        "url": terrain_url,
        "name": terrain_metadata.get("name"),
        "pixel_type": terrain_metadata.get("pixelType"),
        "allow_raster_function": terrain_metadata.get("allowRasterFunction"),
        "max_image_height": terrain_metadata.get("maxImageHeight"),
        "max_image_width": terrain_metadata.get("maxImageWidth"),
        "available": True,
    }
    wetlands = config["inputs"]["wetlands"]
    for source_id, layer in wetlands["layers"].items():
        sources[f"wetlands_{source_id}"] = layer_audit(
            client,
            f"{str(wetlands['service_url']).rstrip('/')}/{int(layer['id'])}",
        )
    roads = config["inputs"]["roads"]
    for source_id, layer in roads["layers"].items():
        sources[f"roads_{source_id}"] = layer_audit(
            client,
            f"{str(roads['service_url']).rstrip('/')}/{int(layer['id'])}",
        )
    sources["buildings_reference"] = layer_audit(
        client,
        str(config["inputs"]["buildings"]["layer_url"]),
    )
    audit = {
        "schema_version": 1,
        "audit": "site_feasibility_sources",
        "source_count": len(sources),
        "sources": sources,
        "all_available": all(value.get("available") for value in sources.values()),
    }
    output = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / "site_feasibility_source_audit.json"
    )
    atomic_write_json(output, audit)
    print(json.dumps(audit, indent=2))
    if not audit["all_available"]:
        raise SystemExit("SITE FEASIBILITY SOURCE AUDIT FAILED")
    print()
    print("SITE FEASIBILITY SOURCE AUDIT PASSED")


if __name__ == "__main__":
    main()
