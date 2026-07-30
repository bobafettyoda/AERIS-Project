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


from analysis.statewide.foundation_join import (
    build_foundation_datasets,
)


def main() -> None:
    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "statewide"
        / "foundation_join.yaml"
    )

    manifest = build_foundation_datasets(
        config_path=config_path,
    )

    print()
    print(
        "Maryland statewide foundation "
        "join complete"
    )

    print(
        json.dumps(
            {
                "counts": (
                    manifest["counts"]
                ),
                "equity_gate_counts_by_tract": (
                    manifest[
                        "equity_gate_counts_by_tract"
                    ]
                ),
                "population_statistics": (
                    manifest[
                        "population_statistics"
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
