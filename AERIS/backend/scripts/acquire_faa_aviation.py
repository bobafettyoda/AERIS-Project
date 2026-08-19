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


from analysis.aviation.faa_nasr import (
    build_faa_aviation_snapshot,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire current-cycle FAA NASR "
            "airport and runway data and build "
            "Maryland-region aviation layers."
        )
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Discard the cached FAA ZIP "
            "and download the configured cycle."
        ),
    )

    return parser.parse_args()


def main() -> None:
    options = arguments()

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "aviation"
        / "faa_nasr.yaml"
    )

    manifest = (
        build_faa_aviation_snapshot(
            config_path=config_path,
            refresh=options.refresh,
        )
    )

    print()
    print(
        "FAA aviation acquisition complete"
    )

    print(
        json.dumps(
            {
                "snapshot_label": (
                    manifest[
                        "snapshot_label"
                    ]
                ),
                "counts": (
                    manifest["counts"]
                ),
                "diagnostics": (
                    manifest[
                        "diagnostics"
                    ]
                ),
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
