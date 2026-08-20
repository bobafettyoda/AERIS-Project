from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
import yaml


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


from analysis.planning.registry import (
    PlanningRegistry,
)
from analysis.planning.statewide_foundations import (
    load_yaml,
    source_definitions,
)


def main() -> None:
    registry_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "planning"
        / "maryland_jurisdictions.yaml"
    )

    planning_config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "planning"
        / "statewide_planning.yaml"
    )

    registry = PlanningRegistry(
        registry_path
    )

    planning_config = load_yaml(
        planning_config_path
    )

    source_audit = {}

    for source in source_definitions(
        planning_config
    ):
        response = requests.get(
            source["layer_url"],
            params={
                "f": "json",
            },
            timeout=120,
        )

        response.raise_for_status()

        metadata = response.json()

        if "error" in metadata:
            raise RuntimeError(
                json.dumps(
                    metadata["error"],
                    indent=2,
                )
            )

        source_audit[
            source["source_id"]
        ] = {
            "layer_url": (
                source["layer_url"]
            ),
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
            "status": (
                "AVAILABLE"
            ),
        }

    audit = {
        "schema_version": 1,
        "audit": (
            "maryland_planning_registry"
        ),
        "registry": (
            registry.coverage_summary()
        ),
        "statewide_sources": (
            source_audit
        ),
        "safeguards": {
            "all_24_jurisdictions_present": (
                len(
                    registry.records
                )
                == 24
            ),
            "local_data_gaps_explicit": (
                True
            ),
            "missing_data_means_no_conflict": (
                False
            ),
        },
    }

    output = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / "planning"
        / "maryland_planning_registry_audit.json"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
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
        "safeguards"
    ][
        "all_24_jurisdictions_present"
    ]:
        raise SystemExit(
            "PLANNING REGISTRY AUDIT FAILED"
        )

    print()
    print(
        "PLANNING REGISTRY AUDIT PASSED"
    )


if __name__ == "__main__":
    main()
