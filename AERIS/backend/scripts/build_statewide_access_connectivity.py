from __future__ import annotations

import argparse
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


from analysis.statewide.access_connectivity_pipeline import (
    build_access_connectivity,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Snapshot major roads and public "
            "fiber coverage, then score the "
            "statewide AERIS grid."
        )
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Discard existing road and fiber "
            "snapshots and download fresh data."
        ),
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse completed ArcGIS page files."
        ),
    )

    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help=(
            "Download and validate source "
            "snapshots without scoring."
        ),
    )

    parser.add_argument(
        "--score-only",
        action="store_true",
        help=(
            "Use cached snapshots and "
            "recalculate grid scores."
        ),
    )

    return parser.parse_args()


def main() -> None:
    options = arguments()

    if (
        options.snapshot_only
        and options.score_only
    ):
        raise SystemExit(
            "--snapshot-only and --score-only "
            "cannot be combined."
        )

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "statewide"
        / "access_connectivity.yaml"
    )

    result = build_access_connectivity(
        config_path,
        refresh=options.refresh,
        resume=options.resume,
        snapshot_only=options.snapshot_only,
        score_only=options.score_only,
    )

    print()
    print(
        "Statewide road and telecom "
        "pipeline complete"
    )

    if result.get(
        "snapshot_only"
    ):
        print(
            json.dumps(
                result,
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "road_methodology": (
                        result[
                            "road_methodology"
                        ]
                    ),
                    "telecom_methodology": (
                        result[
                            "telecom_methodology"
                        ]
                    ),
                    "grid": (
                        result["grid"]
                    ),
                    "known_point_review": (
                        result[
                            "known_point_review"
                        ]
                    ),
                    "outputs": (
                        result["outputs"]
                    ),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
