from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.ops import unary_union

from analysis.statewide.grid_infrastructure_pipeline import (
    StageReporter,
    atomic_write_json,
    build_session,
    download_snapshot,
    envelope_wgs84,
    file_sha256,
    load_yaml,
    nearest_attributes,
    regional_counts,
    request_json,
    resolve_path,
    summary_statistics,
)
from analysis.statewide.scoring import (
    piecewise_linear_series,
)
from app.config import (
    FEMA_FLOODPLAIN_URL,
    PROTECTED_LANDS_URL,
    WATERBODIES_URL,
)


def distance_intersection_flag(
    distances_m: pd.Series,
    tolerance_m: float = 0.01,
) -> pd.Series:
    distance = pd.to_numeric(
        distances_m,
        errors="coerce",
    )

    return (
        distance.notna()
        & distance.le(
            float(tolerance_m)
        )
    )


def within_distance_flag(
    distances_m: pd.Series,
    threshold_m: float,
) -> pd.Series:
    distance = pd.to_numeric(
        distances_m,
        errors="coerce",
    )

    return (
        distance.notna()
        & distance.le(
            float(threshold_m)
        )
    )


def binary_suitability_score(
    excluded: pd.Series,
) -> pd.Series:
    return pd.Series(
        np.where(
            excluded.astype(bool),
            0.0,
            1.0,
        ),
        index=excluded.index,
        dtype=float,
    )


def combine_frames(
    frames: list[gpd.GeoDataFrame],
    target_crs: str,
) -> gpd.GeoDataFrame:
    usable = [
        frame
        for frame in frames
        if not frame.empty
    ]

    if not usable:
        raise RuntimeError(
            "No usable environmental "
            "features were available."
        )

    combined = gpd.GeoDataFrame(
        pd.concat(
            usable,
            ignore_index=True,
            sort=False,
        ),
        geometry="geometry",
        crs=target_crs,
    )

    combined = combined.loc[
        combined.geometry.notna()
        & ~combined.geometry.is_empty
    ].copy()

    combined.geometry = (
        combined.geometry.make_valid()
    )

    return combined



def normalize_geopackage_fields(
    frame: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Make attribute names unique for SQLite/GeoPackage.

    Pandas permits columns such as NAME, Name, and name
    simultaneously. SQLite treats those identifiers as the
    same field, so collisions must be renamed before export.
    """
    original_columns = list(
        frame.columns
    )

    geometry_name = frame.geometry.name

    try:
        geometry_index = (
            original_columns.index(
                geometry_name
            )
        )
    except ValueError as error:
        raise RuntimeError(
            "The active geometry column is "
            "missing from the GeoDataFrame."
        ) from error

    # GeoPackage commonly reserves FID for its
    # internal primary-key field.
    used_names = {
        "fid",
    }

    output_columns: list[str] = []
    renamed_fields: list[
        tuple[str, str]
    ] = []

    for index, column in enumerate(
        original_columns
    ):
        base_name = str(
            column
        ).strip()

        if not base_name:
            base_name = (
                f"field_{index + 1}"
            )

        candidate = base_name
        suffix = 2

        while (
            candidate.casefold()
            in used_names
        ):
            candidate = (
                f"{base_name}_{suffix}"
            )
            suffix += 1

        used_names.add(
            candidate.casefold()
        )

        output_columns.append(
            candidate
        )

        if candidate != str(column):
            renamed_fields.append(
                (
                    str(column),
                    candidate,
                )
            )

    normalized = frame.copy()
    normalized.columns = (
        output_columns
    )

    normalized_geometry_name = (
        output_columns[
            geometry_index
        ]
    )

    normalized = gpd.GeoDataFrame(
        normalized,
        geometry=(
            normalized_geometry_name
        ),
        crs=frame.crs,
    )

    if renamed_fields:
        print(
            (
                "      GeoPackage field-name "
                f"collisions resolved: "
                f"{len(renamed_fields):,}"
            ),
            flush=True,
        )

        for original, replacement in (
            renamed_fields[:20]
        ):
            print(
                (
                    "        "
                    f"{original!r} -> "
                    f"{replacement!r}"
                ),
                flush=True,
            )

        remaining = (
            len(renamed_fields) - 20
        )

        if remaining > 0:
            print(
                (
                    "        ... and "
                    f"{remaining:,} additional "
                    "renamed fields"
                ),
                flush=True,
            )

    return normalized

def write_geopackage(
    frame: gpd.GeoDataFrame,
    output_path: Path,
    layer_name: str,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path.exists():
        output_path.unlink()

    frame = normalize_geopackage_fields(
        frame
    )

    frame.to_file(
        output_path,
        layer=layer_name,
        driver="GPKG",
        index=False,
    )


def source_metadata(
    session,
    layer_url: str,
) -> dict[str, Any]:
    return request_json(
        session,
        layer_url,
    )


def build_environmental_constraints(
    config_path: Path,
    *,
    refresh: bool = False,
    resume: bool = False,
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
    cache = config["cache"]
    snapshot_config = config[
        "snapshot"
    ]

    grid_path = resolve_path(
        project_directory,
        inputs["grid"]["path"],
    )

    decision_model_path = resolve_path(
        project_directory,
        inputs[
            "decision_model"
        ]["path"],
    )

    if not grid_path.exists():
        raise RuntimeError(
            "The access-connectivity grid "
            "does not exist."
        )

    target_crs = str(
        snapshot_config["target_crs"]
    )

    buffer_m = float(
        snapshot_config["buffer_m"]
    )

    page_size = int(
        cache["page_size"]
    )

    reporter = StageReporter(
        total_stages=10
    )

    reporter.stage(
        1,
        "Loading access-connectivity grid",
    )

    grid = gpd.read_file(
        grid_path,
        layer=inputs["grid"]["layer"],
    ).to_crs(target_crs)

    grid = grid.reset_index(
        drop=True
    )

    grid["grid_join_index"] = (
        grid.index
    )

    state_geometry = unary_union(
        list(grid.geometry)
    )

    analysis_buffer = (
        state_geometry.buffer(
            buffer_m
        )
    )

    query_envelope = envelope_wgs84(
        analysis_buffer,
        target_crs,
    )

    reporter.detail(
        f"{len(grid):,} statewide cells"
    )

    session = build_session()

    cache_directory = resolve_path(
        project_directory,
        cache["directory"],
    )

    water_config = config["water"]
    flood_config = config["flood"]
    protected_config = config[
        "protected_lands"
    ]

    stream_url = (
        f"{WATERBODIES_URL.rstrip('/')}/"
        f"{water_config['stream_layer_id']}"
    )

    lake_url = (
        f"{WATERBODIES_URL.rstrip('/')}/"
        f"{water_config['lake_layer_id']}"
    )

    stream_output_config = outputs[
        "streams"
    ]

    lake_output_config = outputs[
        "lakes"
    ]

    stream_output = resolve_path(
        project_directory,
        stream_output_config["path"],
    )

    lake_output = resolve_path(
        project_directory,
        lake_output_config["path"],
    )

    if score_only:
        required_snapshots = [
            stream_output,
            lake_output,
            resolve_path(
                project_directory,
                outputs["sfha"]["path"],
            ),
        ]

        missing = [
            path
            for path in required_snapshots
            if not path.exists()
        ]

        if missing:
            raise RuntimeError(
                "Environmental snapshots are missing: "
                + ", ".join(
                    str(path)
                    for path in missing
                )
            )

    reporter.stage(
        2,
        "Snapshotting detailed streams",
    )

    streams = download_snapshot(
        name="streams",
        session=session,
        layer_url=stream_url,
        desired_fields=(
            water_config[
                "desired_fields"
            ]
        ),
        envelope=query_envelope,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=stream_output,
        output_layer=(
            stream_output_config["layer"]
        ),
        page_directory=(
            cache_directory
            / "streams"
        ),
        page_size=page_size,
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
    )

    streams.frame[
        "water_type"
    ] = "stream"

    reporter.detail(
        (
            f"{streams.snapshot_feature_count:,} "
            "stream features retained"
        )
    )

    reporter.stage(
        3,
        "Snapshotting detailed lakes",
    )

    lakes = download_snapshot(
        name="lakes",
        session=session,
        layer_url=lake_url,
        desired_fields=(
            water_config[
                "desired_fields"
            ]
        ),
        envelope=query_envelope,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=lake_output,
        output_layer=(
            lake_output_config["layer"]
        ),
        page_directory=(
            cache_directory
            / "lakes"
        ),
        page_size=page_size,
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
    )

    lakes.frame[
        "water_type"
    ] = "lake"

    reporter.detail(
        (
            f"{lakes.snapshot_feature_count:,} "
            "lake features retained"
        )
    )

    surface_water = combine_frames(
        [
            streams.frame,
            lakes.frame,
        ],
        target_crs,
    )

    combined_water_output = (
        resolve_path(
            project_directory,
            outputs[
                "combined_water"
            ]["path"],
        )
    )

    write_geopackage(
        surface_water,
        combined_water_output,
        outputs[
            "combined_water"
        ]["layer"],
    )

    reporter.stage(
        4,
        "Snapshotting FEMA special "
        "flood-hazard areas",
    )

    sfha_output_config = outputs[
        "sfha"
    ]

    sfha_output = resolve_path(
        project_directory,
        sfha_output_config["path"],
    )

    sfha = download_snapshot(
        name="sfha",
        session=session,
        layer_url=(
            FEMA_FLOODPLAIN_URL
        ),
        desired_fields=(
            flood_config[
                "desired_fields"
            ]
        ),
        # The source itself is Maryland-wide.
        # Avoid the server's failing combination
        # of statewide geometry plus SFHA filter.
        envelope=None,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=sfha_output,
        output_layer=(
            sfha_output_config["layer"]
        ),
        page_directory=(
            cache_directory
            / "sfha"
        ),
        page_size=int(
            flood_config.get(
                "page_size",
                page_size,
            )
        ),
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
        where=str(
            flood_config["where"]
        ),
    )

    reporter.detail(
        (
            f"{sfha.snapshot_feature_count:,} "
            "SFHA polygons retained"
        )
    )

    reporter.stage(
        5,
        "Snapshotting protected-land layers",
    )

    protected_directory = (
        resolve_path(
            project_directory,
            outputs[
                "protected_snapshot_directory"
            ]["path"],
        )
    )

    protected_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    protected_frames: list[
        gpd.GeoDataFrame
    ] = []

    protected_snapshots = []

    for layer_id in protected_config[
        "layer_ids"
    ]:
        layer_url = (
            f"{PROTECTED_LANDS_URL.rstrip('/')}/"
            f"{int(layer_id)}"
        )

        metadata = source_metadata(
            session,
            layer_url,
        )

        layer_name = str(
            metadata.get(
                "name",
                f"Protected layer {layer_id}",
            )
        )

        output_path = (
            protected_directory
            / (
                f"protected_"
                f"{int(layer_id):02d}.gpkg"
            )
        )

        if (
            score_only
            and not output_path.exists()
        ):
            raise RuntimeError(
                "Missing protected-land snapshot: "
                + str(output_path)
            )

        snapshot = download_snapshot(
            name=(
                f"protected_{int(layer_id):02d}"
            ),
            session=session,
            layer_url=layer_url,
            desired_fields=(
                protected_config[
                    "desired_fields"
                ]
            ),
            envelope=query_envelope,
            analysis_buffer=analysis_buffer,
            target_crs=target_crs,
            output_path=output_path,
            output_layer="protected",
            page_directory=(
                cache_directory
                / "protected"
                / f"{int(layer_id):02d}"
            ),
            page_size=page_size,
            refresh=(
                refresh
                and not score_only
            ),
            resume=resume,
        )

        frame = snapshot.frame.copy()

        frame[
            "protected_layer_id"
        ] = int(layer_id)

        frame[
            "protected_layer_name"
        ] = layer_name

        protected_frames.append(frame)

        protected_snapshots.append(
            {
                "layer_id": int(layer_id),
                "layer_name": layer_name,
                "layer_url": layer_url,
                "snapshot": snapshot,
            }
        )

        reporter.detail(
            (
                f"layer {int(layer_id)}: "
                f"{snapshot.snapshot_feature_count:,} "
                f"features — {layer_name}"
            )
        )

    protected_lands = combine_frames(
        protected_frames,
        target_crs,
    )

    combined_protected_output = (
        resolve_path(
            project_directory,
            outputs[
                "combined_protected"
            ]["path"],
        )
    )

    write_geopackage(
        protected_lands,
        combined_protected_output,
        outputs[
            "combined_protected"
        ]["layer"],
    )

    water_regions = regional_counts(
        surface_water.to_crs(
            "EPSG:4326"
        )
    )

    flood_regions = regional_counts(
        sfha.frame.to_crs(
            "EPSG:4326"
        )
    )

    protected_regions = regional_counts(
        protected_lands.to_crs(
            "EPSG:4326"
        )
    )

    if not all(
        value > 0
        for value in (
            *water_regions.values(),
            *flood_regions.values(),
            *protected_regions.values(),
        )
    ):
        raise RuntimeError(
            "One or more environmental snapshots "
            "do not represent all Maryland regions."
        )

    if snapshot_only:
        return {
            "snapshot_only": True,
            "stream_features": len(
                streams.frame
            ),
            "lake_features": len(
                lakes.frame
            ),
            "sfha_features": len(
                sfha.frame
            ),
            "protected_features": len(
                protected_lands
            ),
            "protected_layer_count": len(
                protected_snapshots
            ),
        }

    reporter.stage(
        6,
        "Calculating environmental proximity "
        "and exclusions",
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

    water_join = nearest_attributes(
        points=analysis_points,
        features=surface_water,
        prefix="water",
        buffer_m=buffer_m,
        desired_attributes=(
            "water_type",
            "LAYER",
            "GNIS_NAME",
            "NAME",
        ),
    )

    sfha_join = nearest_attributes(
        points=analysis_points,
        features=sfha.frame,
        prefix="sfha",
        buffer_m=buffer_m,
        desired_attributes=(
            "FLD_ZONE",
            "ZONE_SUBTY",
            "SFHA_TF",
            "DFIRM_ID",
        ),
    )

    protected_join = nearest_attributes(
        points=analysis_points,
        features=protected_lands,
        prefix="protected",
        buffer_m=buffer_m,
        desired_attributes=(
            "protected_layer_id",
            "protected_layer_name",
            "NAME",
            "DNRName",
            "Own_Name",
            "AREA_NAME",
        ),
    )

    scored_grid = grid.merge(
        water_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid = scored_grid.merge(
        sfha_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid = scored_grid.merge(
        protected_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    model = load_yaml(
        decision_model_path
    )

    water_scoring = model[
        "water_bodies_scoring"
    ]

    water_points = [
        (
            float(
                point["distance_m"]
            ),
            float(
                point["score"]
            ),
        )
        for point
        in water_scoring[
            "distance_points"
        ]
    ]

    maximum_scored_water_distance = max(
        point[0]
        for point in water_points
    )

    beyond_water_score = float(
        water_scoring[
            "beyond_search_radius_score"
        ]
    )

    water_distance = pd.to_numeric(
        scored_grid[
            "water_distance_m"
        ],
        errors="coerce",
    )

    water_score = piecewise_linear_series(
        water_distance,
        water_points,
    )

    water_score = water_score.mask(
        water_distance.gt(
            maximum_scored_water_distance
        ),
        beyond_water_score,
    )

    water_score = water_score.fillna(
        beyond_water_score
    )

    water_hard_excluded = (
        distance_intersection_flag(
            water_distance,
            tolerance_m=float(
                water_config[
                    "direct_intersection_tolerance_m"
                ]
            ),
        )
    )

    water_score = water_score.mask(
        water_hard_excluded,
        0.0,
    )

    protected_distance = pd.to_numeric(
        scored_grid[
            "protected_distance_m"
        ],
        errors="coerce",
    )

    protected_hard_excluded = (
        distance_intersection_flag(
            protected_distance,
            tolerance_m=float(
                protected_config[
                    "direct_intersection_tolerance_m"
                ]
            ),
        )
    )

    protected_score = (
        binary_suitability_score(
            protected_hard_excluded
        )
    )

    sfha_distance = pd.to_numeric(
        scored_grid[
            "sfha_distance_m"
        ],
        errors="coerce",
    )

    flood_buffer_m = float(
        model[
            "hydro_hazard_scoring"
        ].get(
            "sfha_buffer_m",
            91.0,
        )
        if "hydro_hazard_scoring"
        in model
        else 91.0
    )

    inside_sfha = (
        distance_intersection_flag(
            sfha_distance,
            tolerance_m=0.01,
        )
    )

    within_sfha_buffer = (
        within_distance_flag(
            sfha_distance,
            threshold_m=flood_buffer_m,
        )
    )

    hydro_hard_excluded = (
        within_sfha_buffer
    )

    hydro_score = (
        binary_suitability_score(
            hydro_hard_excluded
        )
    )

    scored_grid[
        "water_bodies_score"
    ] = water_score

    scored_grid[
        "water_bodies_weight"
    ] = float(
        model["criteria"][
            "water_bodies"
        ]["weight"]
    )

    scored_grid[
        "water_bodies_weighted_contribution"
    ] = (
        scored_grid[
            "water_bodies_score"
        ]
        * scored_grid[
            "water_bodies_weight"
        ]
    )

    scored_grid[
        "inside_mapped_waterbody"
    ] = water_hard_excluded

    scored_grid[
        "water_hard_excluded"
    ] = water_hard_excluded

    scored_grid[
        "water_bodies_complete"
    ] = True

    scored_grid[
        "protected_areas_score"
    ] = protected_score

    scored_grid[
        "protected_areas_weight"
    ] = float(
        model["criteria"][
            "protected_areas"
        ]["weight"]
    )

    scored_grid[
        "protected_areas_weighted_contribution"
    ] = (
        scored_grid[
            "protected_areas_score"
        ]
        * scored_grid[
            "protected_areas_weight"
        ]
    )

    scored_grid[
        "inside_protected_area"
    ] = protected_hard_excluded

    scored_grid[
        "protected_hard_excluded"
    ] = protected_hard_excluded

    scored_grid[
        "protected_areas_complete"
    ] = True

    scored_grid[
        "hydro_hazard_score"
    ] = hydro_score

    scored_grid[
        "hydro_hazard_weight"
    ] = float(
        model["criteria"][
            "hydro_hazard"
        ]["weight"]
    )

    scored_grid[
        "hydro_hazard_weighted_contribution"
    ] = (
        scored_grid[
            "hydro_hazard_score"
        ]
        * scored_grid[
            "hydro_hazard_weight"
        ]
    )

    scored_grid[
        "inside_sfha"
    ] = inside_sfha

    scored_grid[
        "within_sfha_buffer"
    ] = within_sfha_buffer

    scored_grid[
        "sfha_buffer_m"
    ] = flood_buffer_m

    scored_grid[
        "hydro_hazard_hard_excluded"
    ] = hydro_hard_excluded

    scored_grid[
        "hydro_hazard_complete"
    ] = True

    scored_grid[
        "environmental_hard_excluded"
    ] = (
        scored_grid[
            "water_hard_excluded"
        ]
        | scored_grid[
            "protected_hard_excluded"
        ]
        | scored_grid[
            "hydro_hazard_hard_excluded"
        ]
    )

    previous_partial = (
        "partial_technical_score"
    )

    if previous_partial in scored_grid:
        scored_grid[
            "partial_technical_score_4of8"
        ] = scored_grid[
            previous_partial
        ]

    available_criteria = {
        "population_density": (
            "population_density_score"
        ),
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
        "road_access": (
            "road_access_score"
        ),
        "hydro_hazard": (
            "hydro_hazard_score"
        ),
    }

    available_weight_total = sum(
        float(
            model["criteria"][
                criterion
            ]["weight"]
        )
        for criterion
        in available_criteria
    )

    weighted_sum = pd.Series(
        0.0,
        index=scored_grid.index,
        dtype=float,
    )

    complete = pd.Series(
        True,
        index=scored_grid.index,
        dtype=bool,
    )

    for criterion, column in (
        available_criteria.items()
    ):
        values = pd.to_numeric(
            scored_grid[column],
            errors="coerce",
        )

        complete &= values.notna()

        weighted_sum += (
            values.fillna(0)
            * float(
                model["criteria"][
                    criterion
                ]["weight"]
            )
        )

    scored_grid[
        "partial_technical_weight_total"
    ] = available_weight_total

    scored_grid[
        "partial_technical_score"
    ] = (
        weighted_sum
        / available_weight_total
    ).where(complete)

    scored_grid[
        "partial_effective_score"
    ] = scored_grid[
        "partial_technical_score"
    ].mask(
        scored_grid[
            "environmental_hard_excluded"
        ],
        0.0,
    )

    scored_grid[
        "partial_score_status"
    ] = "7_of_8_criteria"

    scored_grid[
        "partial_heatmap_only"
    ] = True

    base_ready = (
        scored_grid[
            "foundation_screen_ready"
        ].fillna(False)
        & scored_grid[
            "regional_land_threshold_pass"
        ].fillna(False)
        & complete
        & ~scored_grid[
            "environmental_hard_excluded"
        ]
    )

    scored_grid[
        "partial_auto_recommendation_eligible"
    ] = False

    scored_grid[
        "partial_exploration_eligible"
    ] = False

    reporter.detail(
        (
            f"{int(water_hard_excluded.sum()):,} "
            "cells intersect mapped water"
        )
    )

    reporter.detail(
        (
            f"{int(protected_hard_excluded.sum()):,} "
            "cells fall inside protected land"
        )
    )

    reporter.detail(
        (
            f"{int(hydro_hard_excluded.sum()):,} "
            "cells fall inside or within "
            f"{flood_buffer_m:,.0f} m of SFHA"
        )
    )

    reporter.stage(
        7,
        "Writing environmental scored grid",
    )

    scored_output = resolve_path(
        project_directory,
        outputs[
            "scored_grid"
        ]["path"],
    )

    scored_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if scored_output.exists():
        scored_output.unlink()

    scored_grid = gpd.GeoDataFrame(
        scored_grid,
        geometry="geometry",
        crs=target_crs,
    ).drop(
        columns=[
            "grid_join_index",
        ]
    )

    scored_grid.to_file(
        scored_output,
        layer=outputs[
            "scored_grid"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.stage(
        8,
        "Writing seven-criterion preview",
    )

    preview_output = resolve_path(
        project_directory,
        outputs["preview"]["path"],
    )

    preview_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    preview = gpd.GeoDataFrame(
        scored_grid[
            [
                "cell_id",
                "land_fraction",
                "equity_gate",
                "population_density_score",
                "grid_infrastructure_score",
                "telecom_infrastructure_score",
                "road_access_score",
                "water_bodies_score",
                "protected_areas_score",
                "hydro_hazard_score",
                "water_distance_m",
                "protected_distance_m",
                "sfha_distance_m",
                "environmental_hard_excluded",
                "partial_technical_score",
                "partial_effective_score",
                "partial_score_status",
                "partial_auto_recommendation_eligible",
                "partial_exploration_eligible",
            ]
        ].copy(),
        geometry=gpd.points_from_xy(
            scored_grid[
                "analysis_x_m"
            ],
            scored_grid[
                "analysis_y_m"
            ],
        ),
        crs=target_crs,
    ).to_crs("EPSG:4326")

    if preview_output.exists():
        preview_output.unlink()

    preview.to_file(
        preview_output,
        driver="GeoJSON",
        index=False,
    )

    reporter.detail(
        str(preview_output)
    )

    reporter.stage(
        9,
        "Building source and score manifest",
    )

    known_point = config[
        "known_point_review"
    ]

    transformer = Transformer.from_crs(
        "EPSG:4326",
        target_crs,
        always_xy=True,
    )

    known_x, known_y = (
        transformer.transform(
            float(
                known_point[
                    "longitude"
                ]
            ),
            float(
                known_point[
                    "latitude"
                ]
            ),
        )
    )

    known_distance = (
        (
            scored_grid[
                "analysis_x_m"
            ]
            - known_x
        ) ** 2
        + (
            scored_grid[
                "analysis_y_m"
            ]
            - known_y
        ) ** 2
    ) ** 0.5

    known_index = (
        known_distance.idxmin()
    )

    known_cell = scored_grid.loc[
        known_index
    ]

    protected_manifest = [
        {
            "layer_id": item[
                "layer_id"
            ],
            "layer_name": item[
                "layer_name"
            ],
            "layer_url": item[
                "layer_url"
            ],
            "feature_count": item[
                "snapshot"
            ].snapshot_feature_count,
            "selected_fields": item[
                "snapshot"
            ].selected_fields,
            "used_cache": item[
                "snapshot"
            ].used_cache,
            "sha256": file_sha256(
                item[
                    "snapshot"
                ].output_path
            ),
        }
        for item
        in protected_snapshots
    ]

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_environmental_constraints"
        ),
        "snapshot_label": config[
            "snapshot_label"
        ],
        "generated_at_utc": (
            pd.Timestamp.utcnow()
            .isoformat()
        ),
        "snapshot": {
            "target_crs": target_crs,
            "buffer_m": buffer_m,
            "query_envelope_wgs84": (
                query_envelope
            ),
        },
        "sources": {
            "streams": {
                "layer_url": (
                    streams.layer_url
                ),
                "layer_name": (
                    streams.layer_name
                ),
                "feature_count": (
                    streams.snapshot_feature_count
                ),
                "selected_fields": (
                    streams.selected_fields
                ),
                "used_cache": (
                    streams.used_cache
                ),
                "sha256": file_sha256(
                    streams.output_path
                ),
            },
            "lakes": {
                "layer_url": (
                    lakes.layer_url
                ),
                "layer_name": (
                    lakes.layer_name
                ),
                "feature_count": (
                    lakes.snapshot_feature_count
                ),
                "selected_fields": (
                    lakes.selected_fields
                ),
                "used_cache": (
                    lakes.used_cache
                ),
                "sha256": file_sha256(
                    lakes.output_path
                ),
            },
            "sfha": {
                "layer_url": (
                    sfha.layer_url
                ),
                "layer_name": (
                    sfha.layer_name
                ),
                "where": flood_config[
                    "where"
                ],
                "feature_count": (
                    sfha.snapshot_feature_count
                ),
                "selected_fields": (
                    sfha.selected_fields
                ),
                "used_cache": (
                    sfha.used_cache
                ),
                "sha256": file_sha256(
                    sfha.output_path
                ),
            },
            "protected_lands": (
                protected_manifest
            ),
        },
        "regional_feature_counts": {
            "surface_water": (
                water_regions
            ),
            "sfha": flood_regions,
            "protected_lands": (
                protected_regions
            ),
        },
        "scoring": {
            "water_bodies": {
                "weight": float(
                    model["criteria"][
                        "water_bodies"
                    ]["weight"]
                ),
                "method": (
                    water_scoring[
                        "method"
                    ]
                ),
                "distance_points": (
                    water_scoring[
                        "distance_points"
                    ]
                ),
                "beyond_search_radius_score": (
                    beyond_water_score
                ),
                "direct_intersection_exclusion": (
                    True
                ),
            },
            "protected_areas": {
                "weight": float(
                    model["criteria"][
                        "protected_areas"
                    ]["weight"]
                ),
                "direct_intersection_exclusion": (
                    True
                ),
            },
            "hydro_hazard": {
                "weight": float(
                    model["criteria"][
                        "hydro_hazard"
                    ]["weight"]
                ),
                "sfha_buffer_m": (
                    flood_buffer_m
                ),
                "inside_or_buffer_exclusion": (
                    True
                ),
            },
        },
        "grid": {
            "cell_count": len(
                scored_grid
            ),
            "water_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "water_distance_m"
                    ]
                )
            ),
            "protected_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "protected_distance_m"
                    ]
                )
            ),
            "sfha_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "sfha_distance_m"
                    ]
                )
            ),
            "water_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "water_bodies_score"
                    ]
                )
            ),
            "partial_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "partial_technical_score"
                    ]
                )
            ),
            "partial_effective_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "partial_effective_score"
                    ]
                )
            ),
            "partial_technical_weight_total": (
                available_weight_total
            ),
            "partial_criteria": list(
                available_criteria
            ),
            "water_excluded_cells": int(
                scored_grid[
                    "water_hard_excluded"
                ].sum()
            ),
            "protected_excluded_cells": int(
                scored_grid[
                    "protected_hard_excluded"
                ].sum()
            ),
            "hydro_excluded_cells": int(
                scored_grid[
                    "hydro_hazard_hard_excluded"
                ].sum()
            ),
            "any_environmental_exclusion_cells": (
                int(
                    scored_grid[
                        "environmental_hard_excluded"
                    ].sum()
                )
            ),
            "auto_recommendation_eligible_cells": (
                int(
                    scored_grid[
                        "partial_auto_recommendation_eligible"
                    ].sum()
                )
            ),
            "exploration_eligible_cells": (
                int(
                    scored_grid[
                        "partial_exploration_eligible"
                    ].sum()
                )
            ),
            "partial_heatmap_only": True,
            "missing_criterion": (
                "climate"
            ),
        },
        "known_point_review": {
            "input_latitude": (
                known_point[
                    "latitude"
                ]
            ),
            "input_longitude": (
                known_point[
                    "longitude"
                ]
            ),
            "nearest_grid_cell": (
                known_cell[
                    "cell_id"
                ]
            ),
            "representative_point_distance_m": (
                round(
                    float(
                        known_distance.loc[
                            known_index
                        ]
                    ),
                    3,
                )
            ),
            "water_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "water_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "water_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "water_score": round(
                float(
                    known_cell[
                        "water_bodies_score"
                    ]
                ),
                6,
            ),
            "protected_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "protected_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "protected_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "protected_score": round(
                float(
                    known_cell[
                        "protected_areas_score"
                    ]
                ),
                6,
            ),
            "sfha_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "sfha_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "sfha_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "hydro_score": round(
                float(
                    known_cell[
                        "hydro_hazard_score"
                    ]
                ),
                6,
            ),
            "point_evaluator": (
                known_point[
                    "point_evaluator"
                ]
            ),
            "note": known_point[
                "note"
            ],
        },
        "outputs": {
            "combined_water": str(
                combined_water_output.relative_to(
                    project_directory
                )
            ),
            "sfha": str(
                sfha_output.relative_to(
                    project_directory
                )
            ),
            "combined_protected": str(
                combined_protected_output.relative_to(
                    project_directory
                )
            ),
            "scored_grid": str(
                scored_output.relative_to(
                    project_directory
                )
            ),
            "preview": str(
                preview_output.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "combined_water": (
                file_sha256(
                    combined_water_output
                )
            ),
            "sfha": file_sha256(
                sfha_output
            ),
            "combined_protected": (
                file_sha256(
                    combined_protected_output
                )
            ),
            "scored_grid": (
                file_sha256(
                    scored_output
                )
            ),
            "preview": file_sha256(
                preview_output
            ),
        },
    }

    reporter.stage(
        10,
        "Writing environmental manifest",
    )

    manifest_output = resolve_path(
        project_directory,
        outputs["manifest"]["path"],
    )

    atomic_write_json(
        manifest_output,
        manifest,
    )

    reporter.detail(
        str(manifest_output)
    )

    return manifest
