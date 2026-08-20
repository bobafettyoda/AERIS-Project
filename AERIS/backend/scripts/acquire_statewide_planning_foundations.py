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


from analysis.planning.statewide_foundations import (
    acquire_foundations,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire statewide Maryland "
            "planning-context foundations."
        )
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

    manifest = acquire_foundations(
        config_path=config_path,
        refresh=options.refresh,
    )

    print()
    print(
        "Statewide planning foundations complete"
    )

    print(
        json.dumps(
            {
                "sources": {
                    key: {
                        "layer_name": (
                            value[
                                "layer_name"
                            ]
                        ),
                        "feature_count": (
                            value[
                                "feature_count"
                            ]
                        ),
                    }
                    for key, value
                    in manifest[
                        "sources"
                    ].items()
                },
                "written_layers": (
                    manifest[
                        "written_layers"
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
