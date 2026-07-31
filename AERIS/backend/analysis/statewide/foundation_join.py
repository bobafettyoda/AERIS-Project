from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from analysis.statewide.scoring import piecewise_linear_series


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def atomic_write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def load_config(
    config_path: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    required = {
        "inputs",
        "outputs",
        "spatial_join",
        "regional_screening",
        "population_density",
        "equity_gate",
    }

    missing = required - set(config)

    if missing:
        raise RuntimeError(
            "Foundation-join configuration "
            "is missing: "
            + ", ".join(sorted(missing))
        )

    return config


def resolve_path(
    project_directory: Path,
    relative_path: str,
) -> Path:
    return (
        project_directory
        / relative_path
    ).resolve()


def find_column(
    frame: pd.DataFrame,
    expected_name: str,
) -> str:
    lookup = {
        str(column).upper(): str(column)
        for column in frame.columns
    }

    actual = lookup.get(
        expected_name.upper()
    )

    if actual is None:
        raise RuntimeError(
            f"Required field {expected_name} "
            "was not found. Available fields: "
            + ", ".join(
                sorted(
                    str(column)
                    for column in frame.columns
                )
            )
        )

    return actual


def optional_column(
    frame: pd.DataFrame,
    expected_name: str,
) -> str | None:
    lookup = {
        str(column).upper(): str(column)
        for column in frame.columns
    }

    return lookup.get(
        expected_name.upper()
    )


def standardized_geoid(
    series: pd.Series,
) -> pd.Series:
    return (
        series.astype("string")
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.strip()
        .str.zfill(11)
    )


def parse_boolean_flag(
    value: Any,
) -> bool | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    if isinstance(value, bool):
        return value

    if isinstance(
        value,
        (
            int,
            float,
            np.integer,
            np.floating,
        ),
    ):
        if float(value) == 1:
            return True

        if float(value) == 0:
            return False

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    true_values = {
        "1",
        "true",
        "t",
        "yes",
        "y",
        "overburdened",
        "underserved",
    }

    false_values = {
        "0",
        "false",
        "f",
        "no",
        "n",
        "not overburdened",
        "not underserved",
    }

    if normalized in true_values:
        return True

    if normalized in false_values:
        return False

    return None


def equity_gate_status(
    enviroscreen_available: bool,
    overburdened: bool | None,
    underserved: bool | None,
) -> str:
    if not enviroscreen_available:
        return "INSUFFICIENT_DATA"

    if (
        overburdened is None
        and underserved is None
    ):
        return "INSUFFICIENT_DATA"

    if overburdened is True:
        return "HIGH_BURDEN"

    if underserved is True:
        return "CAUTION"

    return "PASS"


def normalize_percentage(
    values: pd.Series,
) -> pd.Series:
    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    numeric = numeric.mask(
        numeric < 0
    )

    numeric = numeric.where(
        numeric > 1,
        numeric * 100,
    )

    return numeric.where(
        numeric <= 100
    )



class StageReporter:
    def __init__(
        self,
        total_stages: int,
    ) -> None:
        self.total_stages = total_stages
        self.started_at = time.monotonic()

    def stage(
        self,
        stage_number: int,
        message: str,
    ) -> None:
        elapsed = (
            time.monotonic()
            - self.started_at
        )

        print(
            (
                f"[{stage_number}/"
                f"{self.total_stages}] "
                f"{message} "
                f"| elapsed {elapsed:,.1f}s"
            ),
            flush=True,
        )

    def detail(
        self,
        message: str,
    ) -> None:
        print(
            f"      {message}",
            flush=True,
        )


def standardize_enviroscreen(
    frame: gpd.GeoDataFrame,
) -> pd.DataFrame:
    geoid_column = find_column(
        frame,
        "GEOID20",
    )

    standardized = pd.DataFrame(
        {
            "GEOID": standardized_geoid(
                frame[geoid_column]
            )
        }
    )

    field_mapping = {
        "P_EJ": "ej_percentile",
        "P_UNDERSERVED": (
            "underserved_percentile"
        ),
        "P_POLLUTIONBURDEN": (
            "pollution_burden_percentile"
        ),
        "P_POLLUTIONENVIRONMENTAL": (
            "environmental_effects_percentile"
        ),
        "P_SENSITIVEPOPULATIONS": (
            "sensitive_populations_percentile"
        ),
        "MINORPCT": (
            "minority_or_hispanic_pct"
        ),
        "LWINCPCT": "low_income_pct",
        "LINGISOPCT": (
            "limited_english_pct"
        ),
    }

    for source_name, target_name in (
        field_mapping.items()
    ):
        source_column = optional_column(
            frame,
            source_name,
        )

        if source_column is None:
            standardized[target_name] = (
                np.nan
            )
        else:
            standardized[target_name] = (
                normalize_percentage(
                    frame[source_column]
                )
            )

    overburdened_column = (
        optional_column(
            frame,
            "OVERBURDENED",
        )
    )

    underserved_column = (
        optional_column(
            frame,
            "UNDERSERVED",
        )
    )

    burden_count_column = (
        optional_column(
            frame,
            "OVERBURDENED_SUM",
        )
    )

    if overburdened_column is None:
        standardized[
            "overburdened_raw"
        ] = None
    else:
        standardized[
            "overburdened_raw"
        ] = frame[
            overburdened_column
        ].astype("string")

    if underserved_column is None:
        standardized[
            "underserved_raw"
        ] = None
    else:
        standardized[
            "underserved_raw"
        ] = frame[
            underserved_column
        ].astype("string")

    standardized["overburdened"] = (
        standardized[
            "overburdened_raw"
        ].map(parse_boolean_flag)
    )

    standardized["underserved"] = (
        standardized[
            "underserved_raw"
        ].map(parse_boolean_flag)
    )

    if burden_count_column is None:
        standardized[
            "overburdened_factor_count"
        ] = np.nan
    else:
        standardized[
            "overburdened_factor_count"
        ] = pd.to_numeric(
            frame[burden_count_column],
            errors="coerce",
        )

    if not standardized[
        "GEOID"
    ].is_unique:
        duplicates = (
            standardized.loc[
                standardized[
                    "GEOID"
                ].duplicated(
                    keep=False
                ),
                "GEOID",
            ]
            .drop_duplicates()
            .tolist()
        )

        raise RuntimeError(
            "MD EnviroScreen contains "
            "duplicate GEOIDs: "
            + ", ".join(
                duplicates[:10]
            )
        )

    return standardized


def build_foundation_datasets(
    config_path: Path,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)

    project_directory = (
        config_path.parents[2]
    )

    inputs = config["inputs"]
    outputs = config["outputs"]

    grid_path = resolve_path(
        project_directory,
        inputs["grid"]["path"],
    )

    tiger_path = resolve_path(
        project_directory,
        inputs["tiger_tracts"]["path"],
    )

    acs_path = resolve_path(
        project_directory,
        inputs["acs_population"]["path"],
    )

    enviroscreen_path = resolve_path(
        project_directory,
        inputs["md_enviroscreen"]["path"],
    )

    source_manifest_path = resolve_path(
        project_directory,
        inputs["source_manifest"]["path"],
    )

    tracts_output_path = resolve_path(
        project_directory,
        outputs[
            "standardized_tracts"
        ]["path"],
    )

    grid_output_path = resolve_path(
        project_directory,
        outputs["enriched_grid"]["path"],
    )

    join_manifest_path = resolve_path(
        project_directory,
        outputs["manifest"]["path"],
    )

    unmatched_path = resolve_path(
        project_directory,
        outputs[
            "unmatched_enviroscreen"
        ]["path"],
    )

    required_files = [
        grid_path,
        tiger_path,
        acs_path,
        enviroscreen_path,
        source_manifest_path,
    ]

    missing_files = [
        path
        for path in required_files
        if not path.exists()
    ]

    if missing_files:
        raise RuntimeError(
            "Required input files are missing: "
            + ", ".join(
                str(path)
                for path in missing_files
            )
        )

    reporter = StageReporter(
        total_stages=7
    )

    target_crs = str(
        config[
            "spatial_join"
        ]["target_crs"]
    )

    reporter.stage(
        1,
        "Loading TIGER tract geometry",
    )

    tracts = gpd.read_file(
        f"zip://{tiger_path}"
    )

    geoid_column = find_column(
        tracts,
        "GEOID",
    )

    state_column = find_column(
        tracts,
        "STATEFP",
    )

    land_area_column = find_column(
        tracts,
        "ALAND",
    )

    tracts = tracts.loc[
        tracts[
            state_column
        ].astype(str)
        .str.zfill(2)
        .eq("24")
    ].copy()

    tracts["GEOID"] = (
        standardized_geoid(
            tracts[geoid_column]
        )
    )

    tracts[
        "tract_land_area_sq_km"
    ] = (
        pd.to_numeric(
            tracts[
                land_area_column
            ],
            errors="coerce",
        )
        / 1_000_000
    )

    if not tracts["GEOID"].is_unique:
        raise RuntimeError(
            "TIGER tract GEOIDs are "
            "not unique."
        )

    tracts = tracts.to_crs(
        target_crs
    )

    reporter.detail(
        f"{len(tracts):,} Maryland tracts loaded"
    )

    reporter.stage(
        2,
        "Joining statewide ACS population",
    )

    acs = pd.read_csv(
        acs_path,
        dtype={
            "GEOID": "string",
            "state": "string",
            "county": "string",
            "tract": "string",
        },
    )

    acs["GEOID"] = (
        standardized_geoid(
            acs["GEOID"]
        )
    )

    if not acs["GEOID"].is_unique:
        raise RuntimeError(
            "ACS GEOIDs are not unique."
        )

    tract_count_before = len(tracts)

    tracts = tracts.merge(
        acs,
        how="left",
        on="GEOID",
        validate="one_to_one",
        indicator="acs_join_status",
    )

    acs_missing_count = int(
        tracts[
            "acs_join_status"
        ].ne("both").sum()
    )

    if acs_missing_count > 0:
        raise RuntimeError(
            f"{acs_missing_count} TIGER tracts "
            "did not match ACS population."
        )

    if len(tracts) != tract_count_before:
        raise RuntimeError(
            "ACS join changed the TIGER "
            "tract count."
        )

    tracts = tracts.drop(
        columns=[
            "acs_join_status",
        ]
    )

    tracts["population"] = (
        pd.to_numeric(
            tracts["population"],
            errors="coerce",
        )
    )

    tracts["population_moe"] = (
        pd.to_numeric(
            tracts["population_moe"],
            errors="coerce",
        )
    )

    invalid_population = (
        tracts["population"].isna()
        | tracts["population"].lt(0)
    )

    if invalid_population.any():
        raise RuntimeError(
            "ACS population contains "
            f"{int(invalid_population.sum())} "
            "invalid values."
        )

    tracts[
        "population_density_people_sq_km"
    ] = (
        tracts["population"]
        / tracts[
            "tract_land_area_sq_km"
        ].replace(
            0,
            np.nan,
        )
    )

    density_config = config[
        "population_density"
    ]

    decision_model_path = resolve_path(
        project_directory,
        density_config[
            "decision_model_path"
        ],
    )

    decision_model = yaml.safe_load(
        decision_model_path.read_text(
            encoding="utf-8"
        )
    )

    population_scoring = (
        decision_model[
            density_config[
                "scoring_section"
            ]
        ]
    )

    population_points = [
        (
            float(point["density"]),
            float(point["score"]),
        )
        for point
        in population_scoring["points"]
    ]

    tracts[
        "population_density_score"
    ] = piecewise_linear_series(
        tracts[
            "population_density_people_sq_km"
        ],
        population_points,
    )

    reporter.detail(
        (
            f"{len(acs):,} ACS records matched; "
            f"statewide population "
            f"{int(tracts['population'].sum()):,}"
        )
    )

    reporter.stage(
        3,
        "Standardizing MD EnviroScreen",
    )

    enviroscreen = gpd.read_file(
        enviroscreen_path
    )

    standardized_enviro = (
        standardize_enviroscreen(
            enviroscreen
        )
    )

    reporter.detail(
        (
            f"{len(standardized_enviro):,} "
            "EnviroScreen records loaded"
        )
    )

    reporter.stage(
        4,
        "Auditing EnviroScreen tract coverage",
    )

    tracts = tracts.merge(
        standardized_enviro,
        how="left",
        on="GEOID",
        validate="one_to_one",
        indicator=(
            "enviroscreen_join_status"
        ),
    )

    tracts[
        "enviroscreen_available"
    ] = tracts[
        "enviroscreen_join_status"
    ].eq("both")

    tracts["equity_gate"] = [
        equity_gate_status(
            enviroscreen_available=bool(
                available
            ),
            overburdened=(
                overburdened
                if isinstance(
                    overburdened,
                    bool,
                )
                else None
            ),
            underserved=(
                underserved
                if isinstance(
                    underserved,
                    bool,
                )
                else None
            ),
        )
        for (
            available,
            overburdened,
            underserved,
        )
        in zip(
            tracts[
                "enviroscreen_available"
            ],
            tracts["overburdened"],
            tracts["underserved"],
            strict=True,
        )
    ]

    unmatched_tracts = tracts.loc[
        ~tracts[
            "enviroscreen_available"
        ],
        [
            "GEOID",
            "NAME",
            "population",
            "population_density_people_sq_km",
        ],
    ].copy()

    unmatched_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    unmatched_tracts.to_csv(
        unmatched_path,
        index=False,
    )

    enviro_geoids = set(
        standardized_enviro["GEOID"]
    )

    tiger_geoids = set(
        tracts["GEOID"]
    )

    extra_enviro_geoids = sorted(
        enviro_geoids - tiger_geoids
    )

    gate_counts = {
        str(key): int(value)
        for key, value
        in tracts[
            "equity_gate"
        ].value_counts(
            dropna=False
        ).items()
    }

    reporter.detail(
        (
            f"{int(tracts['enviroscreen_available'].sum()):,} "
            "tracts matched EnviroScreen"
        )
    )

    reporter.detail(
        (
            f"{len(unmatched_tracts):,} tracts "
            "assigned INSUFFICIENT_DATA"
        )
    )

    reporter.detail(
        (
            "Equity gates: "
            + ", ".join(
                f"{key}={value:,}"
                for key, value
                in sorted(
                    gate_counts.items()
                )
            )
        )
    )

    reporter.stage(
        5,
        "Writing standardized tract layer",
    )

    tracts_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if tracts_output_path.exists():
        tracts_output_path.unlink()

    tracts = tracts.drop(
        columns=[
            "enviroscreen_join_status",
        ]
    )

    tracts.to_file(
        tracts_output_path,
        layer=outputs[
            "standardized_tracts"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        str(tracts_output_path)
    )

    reporter.stage(
        6,
        "Spatially joining tracts to the 1 km grid",
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

    join_fields = [
        "GEOID",
        "population",
        "population_moe",
        "tract_land_area_sq_km",
        "population_density_people_sq_km",
        "population_density_score",
        "enviroscreen_available",
        "equity_gate",
        "overburdened",
        "underserved",
        "overburdened_factor_count",
        "ej_percentile",
        "underserved_percentile",
        "pollution_burden_percentile",
        "environmental_effects_percentile",
        "sensitive_populations_percentile",
        "minority_or_hispanic_pct",
        "low_income_pct",
        "limited_english_pct",
        "geometry",
    ]

    joined = gpd.sjoin(
        analysis_points,
        tracts[join_fields],
        how="left",
        predicate="within",
    )

    duplicate_primary_count = int(
        joined[
            "grid_join_index"
        ].duplicated().sum()
    )

    joined = joined.drop_duplicates(
        subset=[
            "grid_join_index",
        ],
        keep="first",
    )

    unmatched_grid_indices = (
        joined.loc[
            joined["GEOID"].isna(),
            "grid_join_index",
        ]
        .astype(int)
        .tolist()
    )

    nearest_fallback_count = 0

    if unmatched_grid_indices:
        maximum_distance = float(
            config[
                "spatial_join"
            ][
                "nearest_fallback_distance_m"
            ]
        )

        fallback_points = (
            analysis_points.loc[
                analysis_points[
                    "grid_join_index"
                ].isin(
                    unmatched_grid_indices
                )
            ]
        )

        fallback = (
            gpd.sjoin_nearest(
                fallback_points,
                tracts[join_fields],
                how="left",
                max_distance=(
                    maximum_distance
                ),
                distance_col=(
                    "tract_join_distance_m"
                ),
            )
        )

        fallback = (
            fallback.sort_values(
                [
                    "grid_join_index",
                    "tract_join_distance_m",
                ]
            )
            .drop_duplicates(
                subset=[
                    "grid_join_index",
                ],
                keep="first",
            )
        )

        nearest_fallback_count = int(
            fallback["GEOID"]
            .notna()
            .sum()
        )

        joined = joined.loc[
            ~joined[
                "grid_join_index"
            ].isin(
                unmatched_grid_indices
            )
        ]

        joined = pd.concat(
            [
                joined,
                fallback,
            ],
            ignore_index=True,
        )

    joined = joined.sort_values(
        "grid_join_index"
    )

    attribute_columns = [
        column
        for column in join_fields
        if column != "geometry"
    ]

    joined_attributes = (
        pd.DataFrame(
            joined[
                [
                    "grid_join_index",
                    *attribute_columns,
                ]
            ]
        )
    )

    enriched_grid = grid.merge(
        joined_attributes,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    enriched_grid = gpd.GeoDataFrame(
        enriched_grid,
        geometry="geometry",
        crs=target_crs,
    )

    unmatched_grid_count = int(
        enriched_grid[
            "GEOID"
        ].isna().sum()
    )

    minimum_land_fraction = float(
        config[
            "regional_screening"
        ][
            "minimum_land_fraction"
        ]
    )

    enriched_grid[
        "regional_land_threshold_pass"
    ] = enriched_grid[
        "land_fraction"
    ].ge(minimum_land_fraction)

    enriched_grid[
        "foundation_data_complete"
    ] = (
        enriched_grid[
            "population_density_score"
        ].notna()
        & enriched_grid[
            "equity_gate"
        ].notna()
        & enriched_grid[
            "equity_gate"
        ].ne(
            "INSUFFICIENT_DATA"
        )
    )

    enriched_grid[
        "equity_auto_gate_pass"
    ] = enriched_grid[
        "equity_gate"
    ].eq("PASS")

    enriched_grid[
        "foundation_screen_ready"
    ] = (
        enriched_grid[
            "regional_land_threshold_pass"
        ]
        & enriched_grid[
            "foundation_data_complete"
        ]
    )

    enriched_grid = (
        enriched_grid.drop(
            columns=[
                "grid_join_index",
            ]
        )
    )

    grid_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if grid_output_path.exists():
        grid_output_path.unlink()

    enriched_grid.to_file(
        grid_output_path,
        layer=outputs[
            "enriched_grid"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        (
            f"{len(enriched_grid):,} grid cells "
            "written"
        )
    )

    reporter.detail(
        (
            f"{nearest_fallback_count:,} cells "
            "used nearest-tract fallback"
        )
    )

    reporter.detail(
        (
            f"{unmatched_grid_count:,} cells "
            "remain unmatched"
        )
    )

    reporter.stage(
        7,
        "Writing validation manifest",
    )

    source_manifest = json.loads(
        source_manifest_path.read_text(
            encoding="utf-8"
        )
    )

    population_stats = {
        "minimum_density_people_sq_km": (
            round(
                float(
                    tracts[
                        "population_density_people_sq_km"
                    ].min()
                ),
                3,
            )
        ),
        "median_density_people_sq_km": (
            round(
                float(
                    tracts[
                        "population_density_people_sq_km"
                    ].median()
                ),
                3,
            )
        ),
        "maximum_density_people_sq_km": (
            round(
                float(
                    tracts[
                        "population_density_people_sq_km"
                    ].max()
                ),
                3,
            )
        ),
        "statewide_population": int(
            tracts[
                "population"
            ].sum()
        ),
    }

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_foundation_join"
        ),
        "generated_at_utc": utc_now(),
        "target_crs": target_crs,
        "join_method": {
            "primary": (
                "grid representative point "
                "within TIGER tract"
            ),
            "fallback": (
                "nearest TIGER tract within "
                f"{config['spatial_join']['nearest_fallback_distance_m']} "
                "meters"
            ),
        },
        "population_density_method": {
            "source_population": (
                "ACS 2024 5-year "
                "B01003_001E"
            ),
            "source_land_area": (
                "TIGER 2024 ALAND"
            ),
            "formula": (
                "population / "
                "tract_land_area_sq_km"
            ),
            "scoring_source": str(
                decision_model_path.relative_to(
                    project_directory
                )
            ),
            "scoring_method": (
                population_scoring["method"]
            ),
            "scoring_points": [
                {
                    "density_people_sq_km": (
                        density
                    ),
                    "score": score,
                }
                for density, score
                in population_points
            ],
            "known_point_calibration": {
                "density_people_sq_km": (
                    2752.72
                ),
                "expected_score": (
                    0.975272
                ),
            },
        },
        "equity_gate_method": {
            "HIGH_BURDEN": (
                "Official OVERBURDENED "
                "flag is true"
            ),
            "CAUTION": (
                "Official UNDERSERVED "
                "flag is true and "
                "OVERBURDENED is not true"
            ),
            "PASS": (
                "Official flags are available "
                "and neither condition applies"
            ),
            "INSUFFICIENT_DATA": (
                "No matching EnviroScreen "
                "record or flags unavailable"
            ),
            "used_in_technical_score": False,
        },
        "counts": {
            "tiger_tracts": len(tracts),
            "acs_records": len(acs),
            "acs_missing_tracts": (
                acs_missing_count
            ),
            "enviroscreen_records": (
                len(standardized_enviro)
            ),
            "enviroscreen_matched_tracts": (
                int(
                    tracts[
                        "enviroscreen_available"
                    ].sum()
                )
            ),
            "enviroscreen_unmatched_tracts": (
                len(unmatched_tracts)
            ),
            "enviroscreen_extra_geoids": (
                len(extra_enviro_geoids)
            ),
            "grid_cells": len(
                enriched_grid
            ),
            "grid_primary_join_duplicates": (
                duplicate_primary_count
            ),
            "grid_nearest_fallbacks": (
                nearest_fallback_count
            ),
            "grid_unmatched_cells": (
                unmatched_grid_count
            ),
            "foundation_complete_cells": (
                int(
                    enriched_grid[
                        "foundation_data_complete"
                    ].sum()
                )
            ),
            "regional_land_threshold_cells": (
                int(
                    enriched_grid[
                        "regional_land_threshold_pass"
                    ].sum()
                )
            ),
            "foundation_screen_ready_cells": (
                int(
                    enriched_grid[
                        "foundation_screen_ready"
                    ].sum()
                )
            ),
        },
        "equity_gate_counts_by_tract": (
            gate_counts
        ),
        "population_statistics": (
            population_stats
        ),
        "source_snapshot_checksums": {
            name: source.get("sha256")
            for name, source
            in source_manifest.get(
                "sources",
                {}
            ).items()
        },
        "outputs": {
            "standardized_tracts": str(
                tracts_output_path.relative_to(
                    project_directory
                )
            ),
            "enriched_grid": str(
                grid_output_path.relative_to(
                    project_directory
                )
            ),
            "unmatched_enviroscreen": str(
                unmatched_path.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "standardized_tracts": (
                file_sha256(
                    tracts_output_path
                )
            ),
            "enriched_grid": (
                file_sha256(
                    grid_output_path
                )
            ),
        },
    }

    atomic_write_json(
        join_manifest_path,
        manifest,
    )

    reporter.detail(
        str(join_manifest_path)
    )

    return manifest
