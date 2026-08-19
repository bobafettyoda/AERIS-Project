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


from analysis.parcels.pipeline import (
    build_parcel_scope,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire, normalize, and link "
            "Maryland parcels for a candidate "
            "zone or WGS84 bounding box."
        )
    )

    scope = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    scope.add_argument(
        "--zone-id",
        help=(
            "Existing statewide candidate "
            "zone ID."
        ),
    )

    scope.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=(
            "WEST",
            "SOUTH",
            "EAST",
            "NORTH",
        ),
        help=(
            "WGS84 bounding box."
        ),
    )

    parser.add_argument(
        "--scope-name",
        help=(
            "Human-readable name for a "
            "bounding-box scope."
        ),
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Discard the scope cache and "
            "request a fresh parcel snapshot."
        ),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "parcels"
        / "maryland_parcels.yaml"
    )

    bbox = (
        None
        if arguments.bbox is None
        else tuple(
            float(value)
            for value
            in arguments.bbox
        )
    )

    manifest = build_parcel_scope(
        config_path=config_path,
        zone_id=arguments.zone_id,
        bbox=bbox,
        scope_name=(
            arguments.scope_name
        ),
        refresh=arguments.refresh,
    )

    print()
    print(
        "Parcel scope build complete"
    )

    print(
        json.dumps(
            {
                "scope": (
                    manifest["scope"]
                ),
                "counts": (
                    manifest["counts"]
                ),
                "availability_status_counts": (
                    manifest[
                        "availability_status_counts"
                    ]
                ),
                "confidence_counts": (
                    manifest[
                        "confidence_counts"
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
