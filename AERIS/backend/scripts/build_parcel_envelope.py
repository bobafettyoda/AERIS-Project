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


from analysis.parcels.envelope_pipeline import (
    build_scope_envelopes,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build preliminary mapped-"
            "constraint development envelopes "
            "for an existing parcel scope."
        )
    )

    parser.add_argument(
        "scope_id",
        help=(
            "Existing parcel scope ID."
        ),
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Recalculate the envelope even "
            "when cached outputs are current."
        ),
    )

    return parser.parse_args()


def main() -> None:
    options = arguments()

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "parcels"
        / "development_envelopes.yaml"
    )

    manifest = (
        build_scope_envelopes(
            config_path=config_path,
            scope_id=options.scope_id,
            refresh=options.refresh,
        )
    )

    print()
    print(
        "Parcel envelope build complete"
    )

    print(
        json.dumps(
            {
                "scope_id": (
                    manifest[
                        "scope_id"
                    ]
                ),
                "counts": (
                    manifest["counts"]
                ),
                "status_counts": (
                    manifest[
                        "status_counts"
                    ]
                ),
                "statistics": (
                    manifest[
                        "statistics"
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
