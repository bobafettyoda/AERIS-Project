from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import STRtree
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
    inverse_distance_score_series,
    provider_diversity_score_series,
    telecom_proximity_score_series,
    weighted_composite_series,
)
from app.config import (
    FIBER_COVERAGE_LAYER_URL,
    ROAD_INTERSTATES_LAYER_URL,
    ROAD_MARYLAND_ROUTES_LAYER_URL,
    ROAD_US_ROUTES_LAYER_URL,
)


ROAD_SOURCES = {
    "interstate": (
        ROAD_INTERSTATES_LAYER_URL
    ),
    "us_route": (
        ROAD_US_ROUTES_LAYER_URL
    ),
    "maryland_route": (
        ROAD_MARYLAND_ROUTES_LAYER_URL
    ),
}


def text_series(
    frame: pd.DataFrame,
    column_name: str,
) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
        frame[column_name]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def first_available_column(
    frame: pd.DataFrame,
    candidates: Sequence[str],
) -> str | None:
    lookup = {
        str(column).upper(): str(column)
        for column in frame.columns
    }

    for candidate in candidates:
        actual = lookup.get(
            candidate.upper()
        )

        if actual:
            return actual

    return None


def metadata_warning(
    metadata: dict[str, Any],
    phrase: str,
) -> bool:
    text = " ".join(
        str(
            metadata.get(key)
            or ""
        )
        for key in (
            "description",
            "serviceDescription",
            "copyrightText",
        )
    ).lower()

    return phrase.lower() in text


def standardize_fiber_providers(
    fiber: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    result = fiber.copy()

    frn_column = first_available_column(
        result,
        ["FRN"],
    )

    dba_column = first_available_column(
        result,
        ["DBANAME"],
    )

    provider_column = first_available_column(
        result,
        ["PROVNAME"],
    )

    frn = (
        text_series(
            result,
            frn_column,
        )
        if frn_column
        else pd.Series(
            "",
            index=result.index,
            dtype="string",
        )
    )

    dba = (
        text_series(
            result,
            dba_column,
        )
        if dba_column
        else pd.Series(
            "",
            index=result.index,
            dtype="string",
        )
    )

    provider = (
        text_series(
            result,
            provider_column,
        )
        if provider_column
        else pd.Series(
            "",
            index=result.index,
            dtype="string",
        )
    )

    fallback_id = (
        "UNKNOWN-"
        + result[
            "_source_object_id"
        ].astype(str)
    )

    result["provider_key"] = (
        frn.mask(
            frn.eq(""),
            dba,
        )
        .mask(
            lambda values: values.eq(""),
            provider,
        )
        .mask(
            lambda values: values.eq(""),
            fallback_id,
        )
    )

    result["provider_name"] = (
        dba.mask(
            dba.eq(""),
            provider,
        )
        .mask(
            lambda values: values.eq(""),
            "Unknown provider",
        )
    )

    return result


def provider_counts_within_radius(
    points: gpd.GeoDataFrame,
    provider_coverage: gpd.GeoDataFrame,
    radius_m: float,
) -> pd.Series:
    if provider_coverage.empty:
        return pd.Series(
            0,
            index=points.index,
            dtype=int,
        )

    geometries = np.asarray(
        provider_coverage.geometry,
        dtype=object,
    )

    tree = STRtree(geometries)

    point_geometries = np.asarray(
        points.geometry,
        dtype=object,
    )

    pairs = tree.query(
        point_geometries,
        predicate="dwithin",
        distance=float(radius_m),
    )

    counts = np.zeros(
        len(points),
        dtype=np.int32,
    )

    if pairs.size > 0:
        counts = np.bincount(
            pairs[0],
            minlength=len(points),
        ).astype(np.int32)

    return pd.Series(
        counts,
        index=points.index,
        dtype=int,
    )


def source_metadata(
    session,
    layer_url: str,
) -> dict[str, Any]:
    return request_json(
        session,
        layer_url,
    )


def build_access_connectivity(
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
    snapshot_config = config[
        "snapshot"
    ]
    cache_config = config["cache"]

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
            "The grid-infrastructure output "
            "does not exist."
        )

    target_crs = str(
        snapshot_config["target_crs"]
    )

    buffer_m = float(
        snapshot_config["buffer_m"]
    )

    page_size = int(
        cache_config["page_size"]
    )

    reporter = StageReporter(
        total_stages=9
    )

    reporter.stage(
        1,
        "Loading statewide infrastructure grid",
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
        f"{len(grid):,} grid cells"
    )

    session = build_session()

    cache_directory = resolve_path(
        project_directory,
        cache_config["directory"],
    )

    road_config = config["roads"]
    telecom_config = config["telecom"]

    road_snapshots = {}

    road_output_keys = {
        "interstate": (
            "interstate_snapshot"
        ),
        "us_route": (
            "us_route_snapshot"
        ),
        "maryland_route": (
            "maryland_route_snapshot"
        ),
    }

    for stage_number, (
        road_class,
        layer_url,
    ) in enumerate(
        ROAD_SOURCES.items(),
        start=2,
    ):
        reporter.stage(
            stage_number,
            (
                "Snapshotting "
                f"{road_class.replace('_', ' ')}"
            ),
        )

        output_config = outputs[
            road_output_keys[
                road_class
            ]
        ]

        output_path = resolve_path(
            project_directory,
            output_config["path"],
        )

        if (
            score_only
            and not output_path.exists()
        ):
            raise RuntimeError(
                f"{road_class} snapshot "
                "is missing."
            )

        snapshot = download_snapshot(
            name=road_class,
            session=session,
            layer_url=layer_url,
            desired_fields=road_config[
                "desired_fields"
            ],
            envelope=query_envelope,
            analysis_buffer=analysis_buffer,
            target_crs=target_crs,
            output_path=output_path,
            output_layer=output_config[
                "layer"
            ],
            page_directory=(
                cache_directory
                / road_class
            ),
            page_size=page_size,
            refresh=(
                refresh
                and not score_only
            ),
            resume=resume,
        )

        snapshot.frame[
            "road_class"
        ] = road_class

        snapshot.frame[
            "road_source_url"
        ] = layer_url

        road_snapshots[
            road_class
        ] = snapshot

        reporter.detail(
            (
                f"{snapshot.snapshot_feature_count:,} "
                "features retained"
            )
        )

    reporter.stage(
        5,
        "Combining major-road snapshots",
    )

    major_roads = gpd.GeoDataFrame(
        pd.concat(
            [
                snapshot.frame
                for snapshot
                in road_snapshots.values()
            ],
            ignore_index=True,
        ),
        geometry="geometry",
        crs=target_crs,
    )

    major_roads = major_roads.loc[
        major_roads.geometry.notna()
        & ~major_roads.geometry.is_empty
    ].copy()

    combined_road_output = resolve_path(
        project_directory,
        outputs[
            "combined_major_roads"
        ]["path"],
    )

    combined_road_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if combined_road_output.exists():
        combined_road_output.unlink()

    major_roads.to_file(
        combined_road_output,
        layer=outputs[
            "combined_major_roads"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        (
            f"{len(major_roads):,} combined "
            "major-road features"
        )
    )

    reporter.stage(
        6,
        "Snapshotting statewide fiber coverage",
    )

    fiber_output_config = outputs[
        "fiber_snapshot"
    ]

    fiber_output = resolve_path(
        project_directory,
        fiber_output_config["path"],
    )

    if (
        score_only
        and not fiber_output.exists()
    ):
        raise RuntimeError(
            "Fiber snapshot is missing."
        )

    fiber_snapshot = download_snapshot(
        name="fiber_coverage",
        session=session,
        layer_url=(
            FIBER_COVERAGE_LAYER_URL
        ),
        desired_fields=telecom_config[
            "desired_fields"
        ],
        envelope=query_envelope,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=fiber_output,
        output_layer=fiber_output_config[
            "layer"
        ],
        page_directory=(
            cache_directory
            / "fiber_coverage"
        ),
        page_size=page_size,
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
    )

    fiber = standardize_fiber_providers(
        fiber_snapshot.frame
    )

    if fiber_output.exists():
        fiber_output.unlink()

    fiber.to_file(
        fiber_output,
        layer=fiber_output_config[
            "layer"
        ],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        (
            f"{len(fiber):,} coverage polygons; "
            f"{fiber['provider_key'].nunique():,} "
            "distinct provider identifiers"
        )
    )

    road_region_counts = regional_counts(
        major_roads.to_crs(
            "EPSG:4326"
        )
    )

    fiber_region_counts = regional_counts(
        fiber.to_crs(
            "EPSG:4326"
        )
    )

    if not all(
        value > 0
        for value in (
            *road_region_counts.values(),
            *fiber_region_counts.values(),
        )
    ):
        raise RuntimeError(
            "Road or fiber snapshots do not "
            "cover all three Maryland regions."
        )

    if snapshot_only:
        return {
            "snapshot_only": True,
            "major_road_features": (
                len(major_roads)
            ),
            "fiber_features": len(fiber),
            "fiber_providers": int(
                fiber[
                    "provider_key"
                ].nunique()
            ),
            "road_regional_counts": (
                road_region_counts
            ),
            "fiber_regional_counts": (
                fiber_region_counts
            ),
        }

    reporter.stage(
        7,
        "Calculating road and telecom scores",
    )

    model = load_yaml(
        decision_model_path
    )

    preferred = model[
        "preferred_distances"
    ]

    telecom_scoring = model[
        "telecom_infrastructure_scoring"
    ]

    road_weight = float(
        model["criteria"][
            "road_access"
        ]["weight"]
    )

    telecom_weight = float(
        model["criteria"][
            "telecom_infrastructure"
        ]["weight"]
    )

    road_best_m = float(
        preferred["road_m"]
    )

    road_worst_m = 5000.0

    diversity_radius_m = float(
        telecom_config[
            "provider_diversity_radius_m"
        ]
    )

    if buffer_m < max(
        road_worst_m,
        diversity_radius_m,
    ):
        raise RuntimeError(
            "Snapshot buffer is smaller than "
            "a scoring search radius."
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

    road_join = nearest_attributes(
        points=analysis_points,
        features=major_roads,
        prefix="major_road",
        buffer_m=buffer_m,
        desired_attributes=(
            "road_class",
            "ROADNAMESHA",
            "ID_PREFIX",
            "ID_RTE_NO",
            "ROUTEID",
            "ROUTEID_RH",
        ),
    )

    fiber_join = nearest_attributes(
        points=analysis_points,
        features=fiber,
        prefix="fiber",
        buffer_m=buffer_m,
        desired_attributes=(
            "provider_key",
            "provider_name",
            "FRN",
            "DBANAME",
            "PROVNAME",
            "MAXADDOWN",
            "MAXADUP",
        ),
    )

    provider_coverage = (
        fiber[
            [
                "provider_key",
                "provider_name",
                "geometry",
            ]
        ]
        .dissolve(
            by="provider_key",
            as_index=False,
            aggfunc={
                "provider_name": "first",
            },
        )
    )

    provider_counts = (
        provider_counts_within_radius(
            points=analysis_points,
            provider_coverage=(
                provider_coverage
            ),
            radius_m=(
                diversity_radius_m
            ),
        )
    )

    scored_grid = grid.merge(
        road_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid = scored_grid.merge(
        fiber_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid[
        "fiber_provider_count_5km"
    ] = provider_counts.to_numpy()

    scored_grid[
        "road_access_score"
    ] = inverse_distance_score_series(
        scored_grid[
            "major_road_distance_m"
        ].fillna(buffer_m),
        best_m=road_best_m,
        worst_m=road_worst_m,
    )

    scored_grid[
        "road_access_weight"
    ] = road_weight

    scored_grid[
        "road_access_weighted_contribution"
    ] = (
        scored_grid[
            "road_access_score"
        ]
        * road_weight
    )

    scored_grid[
        "road_access_complete"
    ] = True

    scored_grid[
        "telecom_proximity_score"
    ] = telecom_proximity_score_series(
        scored_grid[
            "fiber_distance_m"
        ],
        {
            key: float(value)
            for key, value
            in telecom_scoring[
                "proximity_scores"
            ].items()
        },
    )

    scored_grid[
        "telecom_diversity_score"
    ] = provider_diversity_score_series(
        scored_grid[
            "fiber_provider_count_5km"
        ],
        {
            key: float(value)
            for key, value
            in telecom_scoring[
                "provider_diversity_scores"
            ].items()
        },
    )

    scored_grid[
        "telecom_infrastructure_score"
    ] = weighted_composite_series(
        [
            (
                scored_grid[
                    "telecom_proximity_score"
                ],
                float(
                    telecom_scoring[
                        "proximity_component_weight"
                    ]
                ),
            ),
            (
                scored_grid[
                    "telecom_diversity_score"
                ],
                float(
                    telecom_scoring[
                        "diversity_component_weight"
                    ]
                ),
            ),
        ]
    )

    scored_grid[
        "telecom_infrastructure_weight"
    ] = telecom_weight

    scored_grid[
        "telecom_infrastructure_weighted_contribution"
    ] = (
        scored_grid[
            "telecom_infrastructure_score"
        ]
        * telecom_weight
    )

    scored_grid[
        "telecom_infrastructure_complete"
    ] = True

    scored_grid[
        "telecom_source_quality"
    ] = telecom_config[
        "source_quality"
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
        "road_access": (
            "road_access_score"
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

    partial_weighted_sum = pd.Series(
        0.0,
        index=scored_grid.index,
        dtype=float,
    )

    partial_complete = pd.Series(
        True,
        index=scored_grid.index,
        dtype=bool,
    )

    for (
        criterion,
        column,
    ) in available_criteria.items():
        criterion_values = (
            pd.to_numeric(
                scored_grid[column],
                errors="coerce",
            )
        )

        partial_complete &= (
            criterion_values.notna()
        )

        partial_weighted_sum += (
            criterion_values.fillna(0)
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
        partial_weighted_sum
        / available_weight_total
    ).where(partial_complete)

    scored_grid[
        "partial_score_status"
    ] = "4_of_8_criteria"

    scored_grid[
        "partial_heatmap_only"
    ] = True

    reporter.detail(
        (
            f"{int(scored_grid['major_road_distance_m'].notna().sum()):,} "
            "cells matched a major road "
            f"within {buffer_m:,.0f} m"
        )
    )

    reporter.detail(
        (
            f"{int(scored_grid['fiber_distance_m'].notna().sum()):,} "
            "cells matched fiber coverage "
            f"within {buffer_m:,.0f} m"
        )
    )

    reporter.stage(
        8,
        "Writing scored grid and preview",
    )

    scored_output = resolve_path(
        project_directory,
        outputs[
            "scored_grid"
        ]["path"],
    )

    preview_output = resolve_path(
        project_directory,
        outputs["preview"]["path"],
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

    preview = gpd.GeoDataFrame(
        scored_grid[
            [
                "cell_id",
                "land_fraction",
                "equity_gate",
                "foundation_screen_ready",
                "population_density_score",
                "grid_infrastructure_score",
                "road_access_score",
                "telecom_infrastructure_score",
                "fiber_provider_count_5km",
                "partial_technical_score",
                "partial_technical_weight_total",
                "partial_score_status",
                "partial_heatmap_only",
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
        str(scored_output)
    )

    reporter.detail(
        str(preview_output)
    )

    reporter.stage(
        9,
        "Writing access-connectivity manifest",
    )

    road_metadata = {
        road_class: source_metadata(
            session,
            layer_url,
        )
        for road_class, layer_url
        in ROAD_SOURCES.items()
    }

    fiber_metadata = source_metadata(
        session,
        FIBER_COVERAGE_LAYER_URL,
    )

    road_vintage_warning = any(
        metadata_warning(
            metadata,
            "year 2017",
        )
        for metadata
        in road_metadata.values()
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

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_access_connectivity"
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
        "road_methodology": {
            "method": road_config[
                "methodology"
            ],
            "included_classes": (
                road_config[
                    "included_classes"
                ]
            ),
            "best_m": road_best_m,
            "worst_m": road_worst_m,
            "criterion_weight": (
                road_weight
            ),
            "source_vintage_warning": (
                road_vintage_warning
            ),
            "warning": road_config[
                "source_vintage_warning"
            ],
        },
        "telecom_methodology": {
            "method": telecom_config[
                "methodology"
            ],
            "source_quality": (
                telecom_config[
                    "source_quality"
                ]
            ),
            "warning": telecom_config[
                "source_warning"
            ],
            "provider_diversity_radius_m": (
                diversity_radius_m
            ),
            "criterion_weight": (
                telecom_weight
            ),
            "proximity_component_weight": (
                telecom_scoring[
                    "proximity_component_weight"
                ]
            ),
            "diversity_component_weight": (
                telecom_scoring[
                    "diversity_component_weight"
                ]
            ),
        },
        "sources": {
            "roads": {
                road_class: {
                    "layer_url": (
                        snapshot.layer_url
                    ),
                    "layer_name": (
                        snapshot.layer_name
                    ),
                    "snapshot_feature_count": (
                        snapshot.snapshot_feature_count
                    ),
                    "selected_fields": (
                        snapshot.selected_fields
                    ),
                    "used_cache": (
                        snapshot.used_cache
                    ),
                    "metadata_description": (
                        road_metadata[
                            road_class
                        ].get(
                            "description"
                        )
                    ),
                    "sha256": file_sha256(
                        snapshot.output_path
                    ),
                }
                for road_class, snapshot
                in road_snapshots.items()
            },
            "fiber_coverage": {
                "layer_url": (
                    fiber_snapshot.layer_url
                ),
                "layer_name": (
                    fiber_snapshot.layer_name
                ),
                "snapshot_feature_count": (
                    len(fiber)
                ),
                "distinct_provider_count": (
                    int(
                        fiber[
                            "provider_key"
                        ].nunique()
                    )
                ),
                "selected_fields": (
                    fiber_snapshot.selected_fields
                ),
                "used_cache": (
                    fiber_snapshot.used_cache
                ),
                "metadata_description": (
                    fiber_metadata.get(
                        "description"
                    )
                ),
                "sha256": file_sha256(
                    fiber_output
                ),
            },
        },
        "regional_feature_counts": {
            "major_roads": (
                road_region_counts
            ),
            "fiber_coverage": (
                fiber_region_counts
            ),
        },
        "grid": {
            "cell_count": len(
                scored_grid
            ),
            "major_road_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "major_road_distance_m"
                    ]
                )
            ),
            "road_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "road_access_score"
                    ]
                )
            ),
            "fiber_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "fiber_distance_m"
                    ]
                )
            ),
            "fiber_provider_count_statistics": (
                summary_statistics(
                    scored_grid[
                        "fiber_provider_count_5km"
                    ]
                )
            ),
            "telecom_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "telecom_infrastructure_score"
                    ]
                )
            ),
            "partial_technical_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "partial_technical_score"
                    ]
                )
            ),
            "partial_technical_weight_total": (
                available_weight_total
            ),
            "partial_criteria": list(
                available_criteria
            ),
            "partial_heatmap_only": True,
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
            "major_road_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "major_road_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "major_road_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "statewide_road_score": (
                round(
                    float(
                        known_cell[
                            "road_access_score"
                        ]
                    ),
                    6,
                )
            ),
            "point_evaluator_road_score": (
                known_point[
                    "point_evaluator"
                ][
                    "road_access_score"
                ]
            ),
            "road_method_difference": (
                known_point[
                    "road_method_difference"
                ]
            ),
            "fiber_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "fiber_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "fiber_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "provider_count_5km": (
                int(
                    known_cell[
                        "fiber_provider_count_5km"
                    ]
                )
            ),
            "statewide_telecom_score": (
                round(
                    float(
                        known_cell[
                            "telecom_infrastructure_score"
                        ]
                    ),
                    6,
                )
            ),
            "point_evaluator_telecom_score": (
                known_point[
                    "point_evaluator"
                ][
                    "telecom_infrastructure_score"
                ]
            ),
        },
        "outputs": {
            "combined_major_roads": str(
                combined_road_output.relative_to(
                    project_directory
                )
            ),
            "fiber_snapshot": str(
                fiber_output.relative_to(
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
            "combined_major_roads": (
                file_sha256(
                    combined_road_output
                )
            ),
            "fiber_snapshot": (
                file_sha256(
                    fiber_output
                )
            ),
            "scored_grid": (
                file_sha256(
                    scored_output
                )
            ),
            "preview": (
                file_sha256(
                    preview_output
                )
            ),
        },
    }

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
