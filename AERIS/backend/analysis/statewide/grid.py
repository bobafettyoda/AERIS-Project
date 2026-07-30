from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import yaml
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import unary_union

from analysis.study_area import MarylandStudyArea
from app.config import MARYLAND_BOUNDARY_URL


@dataclass(frozen=True)
class GridBuildResult:
    output_path: Path
    manifest_path: Path
    cell_count: int
    cell_size_m: float
    total_clipped_area_sq_km: float


def load_statewide_config(
    config_path: Path,
) -> dict[str, Any]:
    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    required_sections = (
        "study_area",
        "grid",
        "output",
        "equity",
    )

    missing = [
        section
        for section in required_sections
        if section not in config
    ]

    if missing:
        raise RuntimeError(
            "Statewide configuration is missing: "
            + ", ".join(missing)
        )

    return config


def load_maryland_boundary(
    target_crs: str,
) -> gpd.GeoDataFrame:
    service = MarylandStudyArea(
        layer_url=MARYLAND_BOUNDARY_URL,
    )

    geojson = service.boundary_geojson()

    geometries = [
        shape(feature["geometry"])
        for feature in geojson.get(
            "features",
            [],
        )
        if feature.get("geometry")
    ]

    if not geometries:
        raise RuntimeError(
            "Maryland boundary service returned "
            "no usable geometry."
        )

    merged = unary_union(geometries)

    boundary = gpd.GeoDataFrame(
        {
            "study_area": ["Maryland"],
        },
        geometry=[merged],
        crs="EPSG:4326",
    )

    return boundary.to_crs(target_crs)


def build_square_grid(
    boundary: gpd.GeoDataFrame,
    cell_size_m: float,
    minimum_land_fraction: float,
) -> gpd.GeoDataFrame:
    if cell_size_m <= 0:
        raise ValueError(
            "cell_size_m must be positive."
        )

    if not 0 <= minimum_land_fraction <= 1:
        raise ValueError(
            "minimum_land_fraction must be "
            "between 0 and 1."
        )

    boundary_geometry = (
        boundary.geometry.iloc[0]
    )

    min_x, min_y, max_x, max_y = (
        boundary_geometry.bounds
    )

    start_x = (
        math.floor(min_x / cell_size_m)
        * cell_size_m
    )

    start_y = (
        math.floor(min_y / cell_size_m)
        * cell_size_m
    )

    end_x = (
        math.ceil(max_x / cell_size_m)
        * cell_size_m
    )

    end_y = (
        math.ceil(max_y / cell_size_m)
        * cell_size_m
    )

    to_wgs84 = Transformer.from_crs(
        boundary.crs,
        "EPSG:4326",
        always_xy=True,
    )

    records: list[dict[str, Any]] = []
    geometries = []

    row_count = int(
        round(
            (end_y - start_y)
            / cell_size_m
        )
    )

    column_count = int(
        round(
            (end_x - start_x)
            / cell_size_m
        )
    )

    full_cell_area = cell_size_m**2

    for row in range(row_count):
        y_min = (
            start_y + row * cell_size_m
        )

        y_max = y_min + cell_size_m

        for column in range(column_count):
            x_min = (
                start_x
                + column * cell_size_m
            )

            x_max = x_min + cell_size_m

            full_cell = box(
                x_min,
                y_min,
                x_max,
                y_max,
            )

            if not full_cell.intersects(
                boundary_geometry
            ):
                continue

            clipped = full_cell.intersection(
                boundary_geometry
            )

            if clipped.is_empty:
                continue

            land_fraction = (
                clipped.area
                / full_cell_area
            )

            if (
                land_fraction
                < minimum_land_fraction
            ):
                continue

            analysis_point = (
                clipped.representative_point()
            )

            longitude, latitude = (
                to_wgs84.transform(
                    analysis_point.x,
                    analysis_point.y,
                )
            )

            cell_id = (
                f"MD1K-R{row:03d}-"
                f"C{column:03d}"
            )

            records.append(
                {
                    "cell_id": cell_id,
                    "row": row,
                    "column": column,
                    "cell_size_m": cell_size_m,
                    "land_fraction": round(
                        land_fraction,
                        6,
                    ),
                    "clipped_area_sq_km": (
                        round(
                            clipped.area
                            / 1_000_000,
                            6,
                        )
                    ),
                    "analysis_x_m": round(
                        analysis_point.x,
                        3,
                    ),
                    "analysis_y_m": round(
                        analysis_point.y,
                        3,
                    ),
                    "analysis_lon": round(
                        longitude,
                        7,
                    ),
                    "analysis_lat": round(
                        latitude,
                        7,
                    ),
                }
            )

            geometries.append(clipped)

    if not records:
        raise RuntimeError(
            "No statewide grid cells were "
            "generated."
        )

    grid = gpd.GeoDataFrame(
        records,
        geometry=geometries,
        crs=boundary.crs,
    )

    return grid.sort_values(
        ["row", "column"]
    ).reset_index(drop=True)


def build_from_config(
    config_path: Path,
) -> GridBuildResult:
    config_path = config_path.resolve()
    config = load_statewide_config(
        config_path
    )

    project_directory = (
        config_path.parents[2]
    )

    grid_config = config["grid"]
    output_config = config["output"]

    target_crs = str(
        grid_config["crs"]
    )

    cell_size_m = float(
        grid_config["cell_size_m"]
    )

    minimum_land_fraction = float(
        grid_config[
            "minimum_land_fraction"
        ]
    )

    boundary = load_maryland_boundary(
        target_crs=target_crs,
    )

    grid = build_square_grid(
        boundary=boundary,
        cell_size_m=cell_size_m,
        minimum_land_fraction=(
            minimum_land_fraction
        ),
    )

    output_path = (
        project_directory
        / output_config["geopackage"]
    ).resolve()

    manifest_path = (
        project_directory
        / output_config["manifest"]
    ).resolve()

    layer_name = str(
        output_config["layer"]
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path.exists():
        output_path.unlink()

    grid.to_file(
        output_path,
        layer=layer_name,
        driver="GPKG",
        index=False,
    )

    manifest = {
        "name": config["name"],
        "version": config["version"],
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "study_area": "Maryland",
        "boundary_service": (
            MARYLAND_BOUNDARY_URL
        ),
        "crs": target_crs,
        "cell_size_m": cell_size_m,
        "minimum_land_fraction": (
            minimum_land_fraction
        ),
        "cell_count": len(grid),
        "total_clipped_area_sq_km": (
            round(
                float(
                    grid[
                        "clipped_area_sq_km"
                    ].sum()
                ),
                3,
            )
        ),
        "output": str(
            output_path.relative_to(
                project_directory
            )
        ),
        "layer": layer_name,
    }

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return GridBuildResult(
        output_path=output_path,
        manifest_path=manifest_path,
        cell_count=len(grid),
        cell_size_m=cell_size_m,
        total_clipped_area_sq_km=(
            manifest[
                "total_clipped_area_sq_km"
            ]
        ),
    )
