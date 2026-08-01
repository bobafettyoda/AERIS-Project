from __future__ import annotations

import json
import sys
from pathlib import Path


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


from analysis.statewide.candidate_zones_pipeline import (
    build_candidate_zones_and_audit,
)


def main() -> None:
    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "statewide"
        / "candidate_zones_audit.yaml"
    )

    manifest = (
        build_candidate_zones_and_audit(
            config_path
        )
    )

    print()
    print(
        "Statewide candidate-zone and "
        "bias-audit pipeline complete"
    )

    print(
        json.dumps(
            {
                "counts": (
                    manifest["counts"]
                ),
                "top_zone_ids": (
                    manifest[
                        "top_zone_ids"
                    ]
                ),
                "audit": (
                    manifest["audit"]
                ),
                "required_next_stage": (
                    manifest[
                        "required_next_stage"
                    ]
                ),
                "outputs": (
                    manifest["outputs"]
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
