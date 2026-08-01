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


from analysis.statewide.climate_final_pipeline import (
    build_climate_and_final_grid,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire regional NASA POWER "
            "climatology, calculate the eighth "
            "AERIS criterion, and build the "
            "complete statewide technical model."
        )
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Download a fresh NASA POWER "
            "regional climatology snapshot."
        ),
    )

    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help=(
            "Acquire and validate climate data "
            "without scoring the statewide grid."
        ),
    )

    parser.add_argument(
        "--score-only",
        action="store_true",
        help=(
            "Use the cached NASA snapshot and "
            "recalculate statewide scores."
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
        / "climate_final.yaml"
    )

    manifest = (
        build_climate_and_final_grid(
            config_path,
            refresh=options.refresh,
            snapshot_only=(
                options.snapshot_only
            ),
            score_only=(
                options.score_only
            ),
        )
    )

    print()
    print(
        "Statewide climate and final-model "
        "pipeline complete"
    )

    if manifest.get(
        "snapshot_only"
    ):
        print(
            json.dumps(
                manifest,
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "climate_source": (
                        manifest[
                            "climate_source"
                        ]
                    ),
                    "climate_scoring": (
                        manifest[
                            "climate_scoring"
                        ]
                    ),
                    "final_model": (
                        manifest[
                            "final_model"
                        ]
                    ),
                    "known_point_review": (
                        manifest[
                            "known_point_review"
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
