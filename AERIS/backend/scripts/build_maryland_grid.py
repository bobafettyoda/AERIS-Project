from __future__ import annotations

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


from analysis.statewide.grid import (
    build_from_config,
)


def main() -> None:
    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "statewide"
        / "maryland_1km.yaml"
    )

    result = build_from_config(
        config_path=config_path,
    )

    print(
        "Maryland statewide grid created"
    )

    print(
        "Cells:",
        result.cell_count,
    )

    print(
        "Cell size:",
        f"{result.cell_size_m:.0f} m",
    )

    print(
        "Clipped area:",
        (
            f"{result.total_clipped_area_sq_km:,.1f} "
            "sq km"
        ),
    )

    print(
        "GeoPackage:",
        result.output_path,
    )

    print(
        "Manifest:",
        result.manifest_path,
    )


if __name__ == "__main__":
    main()
