from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from analysis.statewide.grid_infrastructure_pipeline import (
    StageReporter,
    atomic_write_json,
    build_session,
    file_sha256,
    load_yaml,
    resolve_path,
    summary_statistics,
)
from analysis.statewide.scoring import (
    piecewise_linear_series,
    weighted_composite_series,
)


TECHNICAL_CRITERIA = {
    "climate": "climate_score",
    "grid_infrastructure": (
        "grid_infrastructure_score"
    ),
    "telecom_infrastructure": (
        "telecom_infrastructure_score"
    ),
    "protected_areas": (
        "protected_areas_score"
    ),
    "water_bodies": (
        "water_bodies_score"
    ),
    "population_density": (
        "population_density_score"
    ),
    "road_access": (
        "road_access_score"
    ),
    "hydro_hazard": (
        "hydro_hazard_score"
    ),
}


def coerce_boolean_series(
    values: pd.Series,
) -> pd.Series:
    if pd.api.types.is_bool_dtype(
        values
    ):
        return values.fillna(False)

    if pd.api.types.is_numeric_dtype(
        values
    ):
        return (
            pd.to_numeric(
                values,
                errors="coerce",
            )
            .fillna(0)
            .ne(0)
        )

    true_values = {
        "1",
        "true",
        "t",
        "yes",
        "y",
    }

    return (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
        .isin(true_values)
    )


def valid_power_number(
    value: Any,
    *,
    fill_value: float = -999.0,
) -> float | None:
    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if (
        not np.isfinite(number)
        or number == fill_value
    ):
        return None

    return number


def parse_power_regional_climatology(
    payload: dict[str, Any],
    parameter_name: str,
) -> gpd.GeoDataFrame:
    payload_type = payload.get("type")

    if payload_type == "FeatureCollection":
        features = payload.get(
            "features",
            [],
        )

    elif payload_type == "Feature":
        features = [payload]

    elif isinstance(
        payload.get("features"),
        list,
    ):
        features = payload["features"]

    else:
        raise RuntimeError(
            "NASA POWER regional response is "
            "not a FeatureCollection. "
            "Top-level keys: "
            + ", ".join(
                sorted(
                    str(key)
                    for key in payload
                )
            )
        )

    fill_value = valid_power_number(
        payload.get(
            "header",
            {},
        ).get(
            "fill_value"
        )
    )

    if fill_value is None:
        fill_value = -999.0

    records: list[
        dict[str, Any]
    ] = []

    for feature in features:
        if not isinstance(
            feature,
            dict,
        ):
            continue

        geometry = feature.get(
            "geometry",
            {},
        )

        coordinates = geometry.get(
            "coordinates"
        )

        if (
            not isinstance(
                coordinates,
                list,
            )
            or len(coordinates) < 2
        ):
            continue

        longitude = valid_power_number(
            coordinates[0],
            fill_value=fill_value,
        )

        latitude = valid_power_number(
            coordinates[1],
            fill_value=fill_value,
        )

        if (
            longitude is None
            or latitude is None
        ):
            continue

        elevation = (
            valid_power_number(
                coordinates[2],
                fill_value=fill_value,
            )
            if len(coordinates) >= 3
            else None
        )

        properties = feature.get(
            "properties",
            {},
        )

        parameter_values = (
            properties.get(
                "parameter",
                {},
            ).get(
                parameter_name
            )
        )

        if not isinstance(
            parameter_values,
            dict,
        ):
            continue

        annual_mean = valid_power_number(
            parameter_values.get("ANN"),
            fill_value=fill_value,
        )

        july_mean = valid_power_number(
            parameter_values.get("JUL"),
            fill_value=fill_value,
        )

        if (
            annual_mean is None
            or july_mean is None
        ):
            continue

        records.append(
            {
                "power_longitude": (
                    longitude
                ),
                "power_latitude": latitude,
                "source_elevation_m": (
                    elevation
                ),
                "annual_mean_temperature_c": (
                    annual_mean
                ),
                "july_mean_temperature_c": (
                    july_mean
                ),
            }
        )

    if not records:
        raise RuntimeError(
            "NASA POWER regional response "
            "contained no usable climatology points."
        )

    frame = gpd.GeoDataFrame(
        records,
        geometry=gpd.points_from_xy(
            [
                record[
                    "power_longitude"
                ]
                for record in records
            ],
            [
                record[
                    "power_latitude"
                ]
                for record in records
            ],
        ),
        crs="EPSG:4326",
    )

    frame = (
        frame.drop_duplicates(
            subset=[
                "power_longitude",
                "power_latitude",
            ]
        )
        .sort_values(
            [
                "power_latitude",
                "power_longitude",
            ]
        )
        .reset_index(drop=True)
    )

    if (
        frame[
            "annual_mean_temperature_c"
        ].isna().any()
        or frame[
            "july_mean_temperature_c"
        ].isna().any()
    ):
        raise RuntimeError(
            "NASA POWER climatology contains "
            "missing annual or July temperatures."
        )

    return frame


def acquire_power_snapshot(
    *,
    session,
    endpoint: str,
    request_parameters: dict[str, Any],
    output_path: Path,
    refresh: bool,
) -> dict[str, Any]:
    if (
        output_path.exists()
        and not refresh
    ):
        print(
            "      Using cached NASA POWER "
            "regional climatology",
            flush=True,
        )

        return json.loads(
            output_path.read_text(
                encoding="utf-8"
            )
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "      Requesting NASA POWER "
        "regional climatology",
        flush=True,
    )

    print(
        (
            "      Bounds: "
            f"{request_parameters['latitude-min']:.4f}, "
            f"{request_parameters['longitude-min']:.4f} "
            "to "
            f"{request_parameters['latitude-max']:.4f}, "
            f"{request_parameters['longitude-max']:.4f}"
        ),
        flush=True,
    )

    response = session.get(
        endpoint,
        params=request_parameters,
        timeout=240,
    )

    response.raise_for_status()

    content_type = (
        response.headers.get(
            "content-type",
            "",
        ).lower()
    )

    if "json" not in content_type:
        raise RuntimeError(
            "NASA POWER returned a non-JSON "
            f"response: {content_type!r}."
        )

    payload = response.json()

    if "error" in payload:
        raise RuntimeError(
            "NASA POWER returned an error: "
            f"{payload['error']}"
        )

    atomic_write_json(
        output_path,
        payload,
    )

    print(
        (
            "      Snapshot written: "
            f"{output_path}"
        ),
        flush=True,
    )

    return payload


def apply_climate_score(
    frame: pd.DataFrame,
    decision_model: dict[str, Any],
) -> pd.DataFrame:
    result = frame.copy()

    climate_config = (
        decision_model[
            "climate_scoring"
        ]
    )

    annual_points = [
        (
            float(
                point[
                    "temperature_c"
                ]
            ),
            float(point["score"]),
        )
        for point
        in climate_config[
            "annual_mean_temperature_points"
        ]
    ]

    july_points = [
        (
            float(
                point[
                    "temperature_c"
                ]
            ),
            float(point["score"]),
        )
        for point
        in climate_config[
            "july_mean_temperature_points"
        ]
    ]

    annual_component_weight = float(
        climate_config[
            "annual_temperature_component_weight"
        ]
    )

    july_component_weight = float(
        climate_config[
            "july_temperature_component_weight"
        ]
    )

    result[
        "climate_annual_component_score"
    ] = piecewise_linear_series(
        result[
            "annual_mean_temperature_c"
        ],
        annual_points,
    )

    result[
        "climate_july_component_score"
    ] = piecewise_linear_series(
        result[
            "july_mean_temperature_c"
        ],
        july_points,
    )

    result["climate_score"] = (
        weighted_composite_series(
            [
                (
                    result[
                        "climate_annual_component_score"
                    ],
                    annual_component_weight,
                ),
                (
                    result[
                        "climate_july_component_score"
                    ],
                    july_component_weight,
                ),
            ]
        )
    )

    climate_weight = float(
        decision_model[
            "criteria"
        ]["climate"]["weight"]
    )

    result["climate_weight"] = (
        climate_weight
    )

    result[
        "climate_weighted_contribution"
    ] = (
        result["climate_score"]
        * climate_weight
    )

    result["climate_complete"] = (
        result["climate_score"].notna()
    )

    return result


def apply_final_technical_model(
    frame: pd.DataFrame,
    decision_model: dict[str, Any],
) -> pd.DataFrame:
    result = frame.copy()

    criteria_config = (
        decision_model["criteria"]
    )

    missing_columns = [
        column
        for column
        in TECHNICAL_CRITERIA.values()
        if column not in result.columns
    ]

    if missing_columns:
        raise RuntimeError(
            "Final grid is missing criterion "
            "columns: "
            + ", ".join(
                missing_columns
            )
        )

    criterion_weights = {
        criterion: float(
            criteria_config[
                criterion
            ]["weight"]
        )
        for criterion
        in TECHNICAL_CRITERIA
    }

    configured_weight_total = sum(
        criterion_weights.values()
    )

    if abs(
        configured_weight_total
        - 0.9999
    ) > 0.001:
        raise RuntimeError(
            "Configured technical weights total "
            f"{configured_weight_total:.6f}; "
            "expected approximately 0.9999."
        )

    weighted_sum = pd.Series(
        0.0,
        index=result.index,
        dtype=float,
    )

    complete = pd.Series(
        True,
        index=result.index,
        dtype=bool,
    )

    for (
        criterion,
        score_column,
    ) in TECHNICAL_CRITERIA.items():
        score = pd.to_numeric(
            result[score_column],
            errors="coerce",
        )

        invalid = (
            score.notna()
            & ~score.between(
                0.0,
                1.0,
                inclusive="both",
            )
        )

        if invalid.any():
            raise RuntimeError(
                f"{score_column} contains "
                f"{int(invalid.sum()):,} values "
                "outside 0–1."
            )

        complete &= score.notna()

        weighted_sum += (
            score.fillna(0.0)
            * criterion_weights[
                criterion
            ]
        )

    result[
        "technical_weighted_sum"
    ] = weighted_sum.where(
        complete
    )

    result[
        "technical_weight_total"
    ] = configured_weight_total

    result[
        "technical_suitability_score"
    ] = (
        weighted_sum
        / configured_weight_total
    ).where(complete)

    result[
        "technical_score_complete"
    ] = complete

    if (
        "environmental_hard_excluded"
        not in result.columns
    ):
        raise RuntimeError(
            "Environmental exclusion status "
            "is missing from the final grid."
        )

    hard_excluded = (
        coerce_boolean_series(
            result[
                "environmental_hard_excluded"
            ]
        )
    )

    result["hard_excluded"] = (
        hard_excluded
    )

    result[
        "effective_suitability_score"
    ] = result[
        "technical_suitability_score"
    ].mask(
        hard_excluded,
        0.0,
    )

    result["final_model_status"] = (
        np.select(
            [
                ~complete,
                hard_excluded,
            ],
            [
                "INSUFFICIENT_DATA",
                "EXCLUDED",
            ],
            default="COMPLETE",
        )
    )

    land_pass = (
        coerce_boolean_series(
            result[
                "regional_land_threshold_pass"
            ]
        )
        if (
            "regional_land_threshold_pass"
            in result.columns
        )
        else pd.Series(
            False,
            index=result.index,
        )
    )

    equity_gate = (
        result["equity_gate"]
        .astype("string")
        .fillna(
            "INSUFFICIENT_DATA"
        )
    )

    base_screening_eligible = (
        complete
        & land_pass
        & ~hard_excluded
    )

    result[
        "auto_screen_eligible"
    ] = (
        base_screening_eligible
        & equity_gate.eq("PASS")
    )

    result[
        "exploration_screen_eligible"
    ] = (
        base_screening_eligible
        & equity_gate.isin(
            [
                "PASS",
                "CAUTION",
            ]
        )
    )

    # Candidate-zone recommendations remain
    # blocked until the statewide disparate-
    # outcome and concentration audit runs.
    result[
        "bias_audit_pending"
    ] = True

    result[
        "automated_recommendation_ready"
    ] = False

    result[
        "final_heatmap_only"
    ] = True

    return result


def build_climate_and_final_grid(
    config_path: Path,
    *,
    refresh: bool = False,
    snapshot_only: bool = False,
    score_only: bool = False,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_yaml(config_path)

    project_directory = (
        config_path.parents[2]
    )

    inputs = config["inputs"]
    outputs = config["outputs"]
    power_config = config[
        "nasa_power"
    ]
    assignment_config = config[
        "assignment"
    ]

    input_grid_path = resolve_path(
        project_directory,
        inputs["grid"]["path"],
    )

    decision_model_path = (
        resolve_path(
            project_directory,
            inputs[
                "decision_model"
            ]["path"],
        )
    )

    environmental_manifest_path = (
        resolve_path(
            project_directory,
            inputs[
                "environmental_manifest"
            ]["path"],
        )
    )

    raw_snapshot_path = resolve_path(
        project_directory,
        outputs[
            "raw_snapshot"
        ]["path"],
    )

    climate_points_path = (
        resolve_path(
            project_directory,
            outputs[
                "climate_points"
            ]["path"],
        )
    )

    final_grid_path = resolve_path(
        project_directory,
        outputs[
            "final_grid"
        ]["path"],
    )

    preview_path = resolve_path(
        project_directory,
        outputs["preview"]["path"],
    )

    manifest_path = resolve_path(
        project_directory,
        outputs[
            "manifest"
        ]["path"],
    )

    for required_path in (
        input_grid_path,
        decision_model_path,
        environmental_manifest_path,
    ):
        if not required_path.exists():
            raise RuntimeError(
                "Required input is missing: "
                f"{required_path}"
            )

    reporter = StageReporter(
        total_stages=7
    )

    target_crs = str(
        assignment_config[
            "target_crs"
        ]
    )

    reporter.stage(
        1,
        "Loading seven-criterion "
        "environmental grid",
    )

    grid = gpd.read_file(
        input_grid_path,
        layer=inputs["grid"][
            "layer"
        ],
    ).to_crs(target_crs)

    grid = grid.reset_index(
        drop=True
    )

    grid["grid_join_index"] = (
        grid.index
    )

    reporter.detail(
        f"{len(grid):,} statewide cells"
    )

    margin = float(
        power_config[
            "bounding_margin_degrees"
        ]
    )

    latitude_min = float(
        grid[
            "analysis_lat"
        ].min()
        - margin
    )

    latitude_max = float(
        grid[
            "analysis_lat"
        ].max()
        + margin
    )

    longitude_min = float(
        grid[
            "analysis_lon"
        ].min()
        - margin
    )

    longitude_max = float(
        grid[
            "analysis_lon"
        ].max()
        + margin
    )

    request_parameters = {
        "latitude-min": (
            latitude_min
        ),
        "latitude-max": (
            latitude_max
        ),
        "longitude-min": (
            longitude_min
        ),
        "longitude-max": (
            longitude_max
        ),
        "parameters": (
            power_config[
                "parameter"
            ]
        ),
        "community": (
            power_config[
                "community"
            ]
        ),
        "format": (
            power_config["format"]
        ),
    }

    reporter.stage(
        2,
        "Acquiring NASA POWER "
        "regional climatology",
    )

    if (
        score_only
        and not raw_snapshot_path.exists()
    ):
        raise RuntimeError(
            "NASA POWER snapshot is missing."
        )

    payload = acquire_power_snapshot(
        session=build_session(),
        endpoint=str(
            power_config["endpoint"]
        ),
        request_parameters=(
            request_parameters
        ),
        output_path=(
            raw_snapshot_path
        ),
        refresh=(
            refresh
            and not score_only
        ),
    )

    reporter.stage(
        3,
        "Parsing and writing NASA "
        "climate source points",
    )

    climate_points_wgs84 = (
        parse_power_regional_climatology(
            payload,
            parameter_name=str(
                power_config[
                    "parameter"
                ]
            ),
        )
    )

    climate_points = (
        climate_points_wgs84
        .to_crs(target_crs)
    )

    climate_points_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if climate_points_path.exists():
        climate_points_path.unlink()

    climate_points.to_file(
        climate_points_path,
        layer=outputs[
            "climate_points"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        (
            f"{len(climate_points):,} "
            "NASA POWER source points"
        )
    )

    if snapshot_only:
        return {
            "snapshot_only": True,
            "source_point_count": (
                len(climate_points)
            ),
            "raw_snapshot": str(
                raw_snapshot_path
            ),
            "climate_points": str(
                climate_points_path
            ),
        }

    reporter.stage(
        4,
        "Assigning climate values "
        "and calculating climate scores",
    )

    analysis_points = (
        gpd.GeoDataFrame(
            {
                "grid_join_index": (
                    grid[
                        "grid_join_index"
                    ]
                )
            },
            geometry=gpd.points_from_xy(
                grid["analysis_x_m"],
                grid["analysis_y_m"],
            ),
            crs=target_crs,
        )
    )

    climate_join = (
        gpd.sjoin_nearest(
            analysis_points,
            climate_points[
                [
                    "power_longitude",
                    "power_latitude",
                    "source_elevation_m",
                    "annual_mean_temperature_c",
                    "july_mean_temperature_c",
                    "geometry",
                ]
            ],
            how="left",
            distance_col=(
                "climate_source_distance_m"
            ),
        )
        .sort_values(
            [
                "grid_join_index",
                "climate_source_distance_m",
            ]
        )
        .drop_duplicates(
            subset=[
                "grid_join_index",
            ],
            keep="first",
        )
    )

    climate_attributes = pd.DataFrame(
        climate_join[
            [
                "grid_join_index",
                "power_longitude",
                "power_latitude",
                "source_elevation_m",
                "annual_mean_temperature_c",
                "july_mean_temperature_c",
                "climate_source_distance_m",
            ]
        ]
    )

    scored_grid = grid.merge(
        climate_attributes,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    maximum_source_distance = float(
        assignment_config[
            "maximum_source_distance_m"
        ]
    )

    too_far = (
        pd.to_numeric(
            scored_grid[
                "climate_source_distance_m"
            ],
            errors="coerce",
        )
        .gt(maximum_source_distance)
    )

    if too_far.any():
        raise RuntimeError(
            f"{int(too_far.sum()):,} grid cells "
            "are farther than "
            f"{maximum_source_distance:,.0f} m "
            "from a NASA POWER source point."
        )

    decision_model = load_yaml(
        decision_model_path
    )

    scored_grid = apply_climate_score(
        scored_grid,
        decision_model,
    )

    reporter.detail(
        (
            f"{int(scored_grid['climate_complete'].sum()):,} "
            "cells received climate scores"
        )
    )

    reporter.stage(
        5,
        "Calculating complete "
        "eight-criterion suitability",
    )

    final_grid = (
        apply_final_technical_model(
            scored_grid,
            decision_model,
        )
    )

    reporter.detail(
        (
            f"{int(final_grid['technical_score_complete'].sum()):,} "
            "cells have all eight criteria"
        )
    )

    reporter.detail(
        (
            f"{int(final_grid['hard_excluded'].sum()):,} "
            "cells are hard excluded"
        )
    )

    reporter.detail(
        (
            f"{int(final_grid['auto_screen_eligible'].sum()):,} "
            "cells pass the baseline auto-screen gate"
        )
    )

    reporter.detail(
        (
            f"{int(final_grid['exploration_screen_eligible'].sum()):,} "
            "cells pass the exploration gate"
        )
    )

    reporter.stage(
        6,
        "Writing final statewide grid "
        "and heatmap preview",
    )

    final_grid_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if final_grid_path.exists():
        final_grid_path.unlink()

    final_grid = gpd.GeoDataFrame(
        final_grid,
        geometry="geometry",
        crs=target_crs,
    ).drop(
        columns=[
            "grid_join_index",
        ]
    )

    final_grid.to_file(
        final_grid_path,
        layer=outputs[
            "final_grid"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    preview = gpd.GeoDataFrame(
        final_grid[
            [
                "cell_id",
                "land_fraction",
                "equity_gate",
                "annual_mean_temperature_c",
                "july_mean_temperature_c",
                "climate_score",
                "population_density_score",
                "grid_infrastructure_score",
                "telecom_infrastructure_score",
                "protected_areas_score",
                "water_bodies_score",
                "road_access_score",
                "hydro_hazard_score",
                "technical_suitability_score",
                "effective_suitability_score",
                "hard_excluded",
                "final_model_status",
                "auto_screen_eligible",
                "exploration_screen_eligible",
                "bias_audit_pending",
                "automated_recommendation_ready",
            ]
        ].copy(),
        geometry=gpd.points_from_xy(
            final_grid[
                "analysis_x_m"
            ],
            final_grid[
                "analysis_y_m"
            ],
        ),
        crs=target_crs,
    ).to_crs("EPSG:4326")

    preview_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if preview_path.exists():
        preview_path.unlink()

    preview.to_file(
        preview_path,
        driver="GeoJSON",
        index=False,
    )

    reporter.detail(
        str(final_grid_path)
    )

    reporter.detail(
        str(preview_path)
    )

    reporter.stage(
        7,
        "Writing climate and final-model manifest",
    )

    environmental_manifest = (
        json.loads(
            environmental_manifest_path
            .read_text(
                encoding="utf-8"
            )
        )
    )

    known_point = config[
        "known_point_review"
    ]

    known_lon = float(
        known_point["longitude"]
    )

    known_lat = float(
        known_point["latitude"]
    )

    known_distance = (
        (
            final_grid[
                "analysis_lon"
            ]
            - known_lon
        ) ** 2
        + (
            final_grid[
                "analysis_lat"
            ]
            - known_lat
        ) ** 2
    ) ** 0.5

    known_index = (
        known_distance.idxmin()
    )

    known_cell = (
        final_grid.loc[
            known_index
        ]
    )

    technical_weights = {
        criterion: float(
            decision_model[
                "criteria"
            ][criterion]["weight"]
        )
        for criterion
        in TECHNICAL_CRITERIA
    }

    model_weight_total = sum(
        technical_weights.values()
    )

    complete_count = int(
        final_grid[
            "technical_score_complete"
        ].sum()
    )

    incomplete_count = (
        len(final_grid)
        - complete_count
    )

    source_header = payload.get(
        "header",
        {},
    )

    source_parameter = payload.get(
        "parameters",
        {},
    ).get(
        str(
            power_config[
                "parameter"
            ]
        ),
        {},
    )

    known_climate_score = (
        None
        if pd.isna(
            known_cell[
                "climate_score"
            ]
        )
        else round(
            float(
                known_cell[
                    "climate_score"
                ]
            ),
            6,
        )
    )

    point_climate_score = float(
        known_point[
            "point_evaluator"
        ]["climate_score"]
    )

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_climate_and_final_model"
        ),
        "snapshot_label": config[
            "snapshot_label"
        ],
        "generated_at_utc": (
            pd.Timestamp.utcnow()
            .isoformat()
        ),
        "climate_source": {
            "provider": "NASA POWER",
            "endpoint": (
                power_config[
                    "endpoint"
                ]
            ),
            "request_parameters": (
                request_parameters
            ),
            "parameter": (
                power_config[
                    "parameter"
                ]
            ),
            "community": (
                power_config[
                    "community"
                ]
            ),
            "format": (
                power_config["format"]
            ),
            "source_point_count": (
                len(climate_points)
            ),
            "source_products": (
                source_header.get(
                    "sources"
                )
            ),
            "climatology_period": (
                source_header.get(
                    "range"
                )
            ),
            "api": source_header.get(
                "api"
            ),
            "time_standard": (
                source_header.get(
                    "time_standard"
                )
            ),
            "fill_value": (
                source_header.get(
                    "fill_value"
                )
            ),
            "units": (
                source_parameter.get(
                    "units"
                )
            ),
            "long_name": (
                source_parameter.get(
                    "longname"
                )
            ),
            "raw_snapshot_sha256": (
                file_sha256(
                    raw_snapshot_path
                )
            ),
        },
        "assignment": {
            "method": (
                assignment_config[
                    "method"
                ]
            ),
            "target_crs": target_crs,
            "maximum_source_distance_m": (
                maximum_source_distance
            ),
            "distance_statistics_m": (
                summary_statistics(
                    final_grid[
                        "climate_source_distance_m"
                    ]
                )
            ),
        },
        "climate_scoring": {
            "method": (
                decision_model[
                    "climate_scoring"
                ]["method"]
            ),
            "criterion_weight": (
                technical_weights[
                    "climate"
                ]
            ),
            "annual_component_weight": (
                decision_model[
                    "climate_scoring"
                ][
                    "annual_temperature_component_weight"
                ]
            ),
            "july_component_weight": (
                decision_model[
                    "climate_scoring"
                ][
                    "july_temperature_component_weight"
                ]
            ),
            "annual_temperature_points": (
                decision_model[
                    "climate_scoring"
                ][
                    "annual_mean_temperature_points"
                ]
            ),
            "july_temperature_points": (
                decision_model[
                    "climate_scoring"
                ][
                    "july_mean_temperature_points"
                ]
            ),
            "score_statistics": (
                summary_statistics(
                    final_grid[
                        "climate_score"
                    ]
                )
            ),
        },
        "final_model": {
            "criteria": (
                list(
                    TECHNICAL_CRITERIA
                )
            ),
            "score_columns": (
                TECHNICAL_CRITERIA
            ),
            "weights": (
                technical_weights
            ),
            "configured_weight_total": (
                model_weight_total
            ),
            "weight_normalization": (
                bool(
                    config["model"][
                        "final_weight_normalization"
                    ]
                )
            ),
            "technical_score_statistics": (
                summary_statistics(
                    final_grid[
                        "technical_suitability_score"
                    ]
                )
            ),
            "effective_score_statistics": (
                summary_statistics(
                    final_grid[
                        "effective_suitability_score"
                    ]
                )
            ),
            "cell_count": len(
                final_grid
            ),
            "complete_cells": (
                complete_count
            ),
            "insufficient_data_cells": (
                incomplete_count
            ),
            "hard_excluded_cells": int(
                final_grid[
                    "hard_excluded"
                ].sum()
            ),
            "auto_screen_eligible_cells": (
                int(
                    final_grid[
                        "auto_screen_eligible"
                    ].sum()
                )
            ),
            "exploration_screen_eligible_cells": (
                int(
                    final_grid[
                        "exploration_screen_eligible"
                    ].sum()
                )
            ),
            "bias_audit_pending": (
                bool(
                    config["model"][
                        "bias_audit_pending"
                    ]
                )
            ),
            "automated_recommendation_ready": (
                False
            ),
            "demographic_fields_used_in_technical_score": (
                False
            ),
        },
        "known_point_review": {
            "input_latitude": (
                known_lat
            ),
            "input_longitude": (
                known_lon
            ),
            "nearest_grid_cell": (
                known_cell[
                    "cell_id"
                ]
            ),
            "grid_cell_latitude": (
                float(
                    known_cell[
                        "analysis_lat"
                    ]
                )
            ),
            "grid_cell_longitude": (
                float(
                    known_cell[
                        "analysis_lon"
                    ]
                )
            ),
            "annual_mean_temperature_c": (
                float(
                    known_cell[
                        "annual_mean_temperature_c"
                    ]
                )
            ),
            "july_mean_temperature_c": (
                float(
                    known_cell[
                        "july_mean_temperature_c"
                    ]
                )
            ),
            "statewide_climate_score": (
                known_climate_score
            ),
            "point_evaluator_climate_score": (
                point_climate_score
            ),
            "absolute_score_difference": (
                None
                if known_climate_score
                is None
                else round(
                    abs(
                        known_climate_score
                        - point_climate_score
                    ),
                    6,
                )
            ),
            "technical_suitability_score": (
                None
                if pd.isna(
                    known_cell[
                        "technical_suitability_score"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "technical_suitability_score"
                        ]
                    ),
                    6,
                )
            ),
            "hard_excluded": bool(
                known_cell[
                    "hard_excluded"
                ]
            ),
            "equity_gate": str(
                known_cell[
                    "equity_gate"
                ]
            ),
            "note": known_point[
                "note"
            ],
        },
        "environmental_input": {
            "manifest": str(
                environmental_manifest_path
                .relative_to(
                    project_directory
                )
            ),
            "sha256": file_sha256(
                environmental_manifest_path
            ),
            "environmental_exclusion_cells": (
                environmental_manifest[
                    "grid"
                ][
                    "any_environmental_exclusion_cells"
                ]
            ),
        },
        "outputs": {
            "raw_snapshot": str(
                raw_snapshot_path
                .relative_to(
                    project_directory
                )
            ),
            "climate_points": str(
                climate_points_path
                .relative_to(
                    project_directory
                )
            ),
            "final_grid": str(
                final_grid_path
                .relative_to(
                    project_directory
                )
            ),
            "preview": str(
                preview_path
                .relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "climate_points": (
                file_sha256(
                    climate_points_path
                )
            ),
            "final_grid": file_sha256(
                final_grid_path
            ),
            "preview": file_sha256(
                preview_path
            ),
        },
    }

    atomic_write_json(
        manifest_path,
        manifest,
    )

    reporter.detail(
        str(manifest_path)
    )

    return manifest
