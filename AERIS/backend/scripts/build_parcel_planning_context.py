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


from analysis.planning.planning_pipeline import (
    build_planning_context,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build statewide parcel-level "
            "planning and entitlement context."
        )
    )

    parser.add_argument(
        "scope_id",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    options = arguments()

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "planning"
        / "statewide_planning.yaml"
    )

    manifest = build_planning_context(
        config_path=config_path,
        scope_id=options.scope_id,
        refresh=options.refresh,
    )

    print()
    print(
        "Parcel planning-context build complete"
    )

    print(
        json.dumps(
            {
                "scope_id": (
                    manifest["scope_id"]
                ),
                "counts": (
                    manifest["counts"]
                ),
                "planning_review_status_counts": (
                    manifest[
                        "planning_review_status_counts"
                    ]
                ),
                "authority_status_counts": (
                    manifest[
                        "authority_status_counts"
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
