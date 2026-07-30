from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
import yaml
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import unary_union

from app.config import (
    MARYLAND_LAND_BOUNDARIES_URL,
)


@dataclass(frozen=True)
class GridBuildResult:
    output_path: Path
    manifest_path: Path
    cell_count: int
    cell_size_m: float
    physical_land_boundary_area_sq_km: float
    total_clipped_area_sq_km: float


def load_config(
    config_path: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    for section in (
        "study_area",
        "grid",
        "output",
    ):
        if section not in config:
            raise RuntimeError(
                f"Missing configuration section: {section}"
            )

    return config


def load_land_boundary(
    target_crs: str,
) -> tuple[
    gpd.GeoDataFrame,
    str,
    int,
]:
    feature_url = (
        MARYLAND_LAND_BOUNDARIES_URL
        .rstrip("/")
    )

    layer_urls = [
        feature_url,
        feature_url.replace(
            "/FeatureServer/1",
            "/MapServer/1",
        ),
    ]

    errors: list[str] = []

    for layer_url in layer_urls:
        try:
            response = requests.post(
                f"{layer_url}/query",
                data={
                    "f": "geojson",
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "true",
                    "returnTrueCurves": "false",
                    "outSR": "4326",
                    "resultRecordCount": "50",
                },
                headers={
                    "User-Agent": "AERIS/0.2",
                },
                timeout=180,
            )

            if response.status_code >= 500:
                errors.append(
                    f"{layer_url}: "
                    f"HTTP {response.status_code}"
                )
                continue

            response.raise_for_status()
            payload = response.json()

            if "error" in payload:
                errors.append(
                    f"{layer_url}: "
                    f"{payload['error']}"
                )
                continue

            features = payload.get(
                "features",
                [],
            )

            if not features:
                errors.append(
                    f"{layer_url}: no features"
                )
                continue

            counties = (
                gpd.GeoDataFrame
                .from_features(
                    features,
                    crs="EPSG:4326",
                )
            )

            usable = [
                geometry
                for geometry
                in counties.geometry
                if geometry is not None
                and not geometry.is_empty
            ]

            if not usable:
                errors.append(
                    f"{layer_url}: "
                    "no usable geometry"
                )
                continue

            merged = unary_union(usable)

            if not merged.is_valid:
                merged = merged.buffer(0)

            boundary = gpd.GeoDataFrame(
                {
                    "study_area": [
                        "Maryland land area"
                    ],
                },
                geometry=[merged],
                crs="EPSG:4326",
            ).to_crs(target_crs)

            return (
                boundary,
                layer_url,
                len(features),
            )

        except Exception as error:
            errors.append(
                f"{layer_url}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    raise RuntimeError(
        "Unable to load Maryland land boundary. "
        + " | ".join(errors)
    )


def build_grid(
    boundary: gpd.GeoDataFrame,
    cell_size_m: float,
    minimum_land_fraction: float,
) -> gpd.GeoDataFrame:
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

    row_count = int(
        (end_y - start_y)
        / cell_size_m
    )

    column_count = int(
        (end_x - start_x)
        / cell_size_m
    )

    full_cell_area = cell_size_m**2

    to_wgs84 = Transformer.from_crs(
        boundary.crs,
        "EPSG:4326",
        always_xy=True,
    )

    records: list[dict[str, Any]] = []
    geometries = []

    for row in range(row_count):
        y_min = (
            start_y
            + row * cell_size_m
        )

        for column in range(
            column_count
        ):
            x_min = (
                start_x
                + column * cell_size_m
            )

            full_cell = box(
                x_min,
                y_min,
                x_min + cell_size_m,
                y_min + cell_size_m,
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

            records.append(
                {
                    "cell_id": (
                        f"MD1K-R{row:03d}-"
                        f"C{column:03d}"
                    ),
                    "row": row,
                    "column": column,
                    "cell_size_m": (
                        cell_size_m
                    ),
                    "land_fraction": round(
                        land_fraction,
                        6,
                    ),
                    "clipped_area_sq_km": round(
                        clipped.area
                        / 1_000_000,
                        6,
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
            "No Maryland grid cells were generated."
        )

    grid = gpd.GeoDataFrame(
        records,
        geometry=geometries,
        crs=boundary.crs,
    )

    return (
        grid.sort_values(
            ["row", "column"]
        )
        .reset_index(drop=True)
    )


def build_from_config(
    config_path: Path,
) -> GridBuildResult:
    config_path = config_path.resolve()
    config = load_config(config_path)

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

    (
        boundary,
        source_url,
        source_feature_count,
    ) = load_land_boundary(
        target_crs
    )

    physical_area = float(
        boundary.geometry.iloc[0].area
        / 1_000_000
    )

    grid = build_grid(
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

    retained_area = float(
        grid[
            "clipped_area_sq_km"
        ].sum()
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
        "boundary_type": "land_only",
        "land_boundary_service": (
            source_url
        ),
        "boundary_source_feature_count": (
            source_feature_count
        ),
        "physical_land_boundary_area_sq_km": (
            round(physical_area, 3)
        ),
        "crs": target_crs,
        "cell_size_m": cell_size_m,
        "minimum_land_fraction": (
            minimum_land_fraction
        ),
        "cell_count": len(grid),
        "total_clipped_area_sq_km": (
            round(retained_area, 3)
        ),
        "omitted_sliver_area_sq_km": (
            round(
                max(
                    0.0,
                    physical_area
                    - retained_area,
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
        physical_land_boundary_area_sq_km=(
            round(physical_area, 3)
        ),
        total_clipped_area_sq_km=(
            round(retained_area, 3)
        ),
    )
