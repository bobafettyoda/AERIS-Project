from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


AERIS_ROOT = (
    Path(__file__).resolve().parents[2]
)

GRID_PATH = (
    AERIS_ROOT
    / "data/derived/"
    "maryland_grid_1km_final.gpkg"
)

MANIFEST_PATH = (
    AERIS_ROOT
    / "data/manifests/"
    "statewide_climate_final.json"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def as_bool(
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

    return (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
        .isin(
            {
                "1",
                "true",
                "t",
                "yes",
                "y",
            }
        )
    )


def main() -> None:
    require(
        GRID_PATH.exists(),
        f"Missing final grid: {GRID_PATH}",
    )

    require(
        MANIFEST_PATH.exists(),
        f"Missing manifest: {MANIFEST_PATH}",
    )

    frame = gpd.read_file(
        GRID_PATH,
        layer="cells",
    )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    final_model = manifest[
        "final_model"
    ]

    required_columns = {
        "cell_id",
        "annual_mean_temperature_c",
        "july_mean_temperature_c",
        "climate_score",
        "technical_weighted_sum",
        "technical_suitability_score",
        "effective_suitability_score",
        "technical_score_complete",
        "hard_excluded",
        "final_model_status",
        "auto_screen_eligible",
        "exploration_screen_eligible",
        "bias_audit_pending",
        "automated_recommendation_ready",
    }

    missing_columns = (
        required_columns
        - set(frame.columns)
    )

    require(
        not missing_columns,
        (
            "Final grid is missing columns: "
            + ", ".join(
                sorted(missing_columns)
            )
        ),
    )

    require(
        len(frame)
        == int(
            final_model["cell_count"]
        ),
        "Final-grid count does not match manifest.",
    )

    require(
        frame["cell_id"].is_unique,
        "Grid cell IDs are not unique.",
    )

    require(
        frame.geometry.notna().all(),
        "Final grid contains null geometries.",
    )

    require(
        (
            ~frame.geometry.is_empty
        ).all(),
        "Final grid contains empty geometries.",
    )

    require(
        frame.geometry.is_valid.all(),
        "Final grid contains invalid geometries.",
    )

    score_columns = [
        "climate_score",
        "grid_infrastructure_score",
        "telecom_infrastructure_score",
        "protected_areas_score",
        "water_bodies_score",
        "population_density_score",
        "road_access_score",
        "hydro_hazard_score",
        "technical_suitability_score",
        "effective_suitability_score",
    ]

    for column in score_columns:
        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).dropna()

        require(
            values.between(
                0.0,
                1.0,
                inclusive="both",
            ).all(),
            (
                f"{column} contains values "
                "outside 0–1."
            ),
        )

    climate_complete = as_bool(
        frame[
            "climate_complete"
        ]
    )

    technical_complete = as_bool(
        frame[
            "technical_score_complete"
        ]
    )

    hard_excluded = as_bool(
        frame["hard_excluded"]
    )

    auto_screen = as_bool(
        frame[
            "auto_screen_eligible"
        ]
    )

    exploration_screen = as_bool(
        frame[
            "exploration_screen_eligible"
        ]
    )

    bias_pending = as_bool(
        frame["bias_audit_pending"]
    )

    recommendation_ready = as_bool(
        frame[
            "automated_recommendation_ready"
        ]
    )

    require(
        climate_complete.all(),
        "Some cells are missing climate scores.",
    )

    require(
        frame.loc[
            hard_excluded,
            "effective_suitability_score",
        ].eq(0).all(),
        (
            "Hard-excluded cells do not all "
            "have an effective score of zero."
        ),
    )

    nonexcluded_complete = (
        ~hard_excluded
        & technical_complete
    )

    difference = (
        frame.loc[
            nonexcluded_complete,
            "technical_suitability_score",
        ]
        - frame.loc[
            nonexcluded_complete,
            "effective_suitability_score",
        ]
    ).abs()

    require(
        difference.le(0.000001).all(),
        (
            "Nonexcluded effective scores differ "
            "from technical scores."
        ),
    )

    require(
        (
            ~auto_screen
            | frame[
                "equity_gate"
            ].astype(str).eq("PASS")
        ).all(),
        "Auto screening does not respect equity PASS.",
    )

    require(
        (
            ~auto_screen
            | ~hard_excluded
        ).all(),
        "Auto screening includes excluded cells.",
    )

    require(
        (
            ~auto_screen
            | technical_complete
        ).all(),
        "Auto screening includes incomplete cells.",
    )

    require(
        (
            ~exploration_screen
            | frame[
                "equity_gate"
            ].astype(str).isin(
                [
                    "PASS",
                    "CAUTION",
                ]
            )
        ).all(),
        (
            "Exploration screening includes "
            "blocked equity gates."
        ),
    )

    require(
        bias_pending.all(),
        "Not all cells are marked bias-audit pending.",
    )

    require(
        (~recommendation_ready).all(),
        (
            "Automated recommendations were enabled "
            "before the statewide bias audit."
        ),
    )

    criteria = set(
        final_model["criteria"]
    )

    expected_criteria = {
        "climate",
        "grid_infrastructure",
        "telecom_infrastructure",
        "protected_areas",
        "water_bodies",
        "population_density",
        "road_access",
        "hydro_hazard",
    }

    require(
        criteria == expected_criteria,
        "Final model does not contain all eight criteria.",
    )

    require(
        abs(
            float(
                final_model[
                    "configured_weight_total"
                ]
            )
            - 0.9999
        )
        < 0.001,
        "Final model weights do not total 0.9999.",
    )

    require(
        final_model[
            "demographic_fields_used_in_technical_score"
        ]
        is False,
        (
            "Manifest indicates demographic fields "
            "were used in technical scoring."
        ),
    )

    assignment_distance = pd.to_numeric(
        frame[
            "climate_source_distance_m"
        ],
        errors="coerce",
    )

    maximum_allowed = float(
        manifest[
            "assignment"
        ][
            "maximum_source_distance_m"
        ]
    )

    require(
        assignment_distance.notna().all(),
        "Some cells lack a climate source distance.",
    )

    require(
        assignment_distance.le(
            maximum_allowed
        ).all(),
        (
            "Some cells exceed the maximum "
            "climate assignment distance."
        ),
    )

    known_difference = (
        manifest[
            "known_point_review"
        ][
            "absolute_score_difference"
        ]
    )

    require(
        known_difference is not None,
        "Known-point climate comparison is missing.",
    )

    require(
        float(known_difference) <= 0.10,
        (
            "Known-point climate-score difference "
            "exceeds 0.10."
        ),
    )

    complete_count = int(
        technical_complete.sum()
    )

    incomplete_count = (
        len(frame) - complete_count
    )

    print()
    print(
        "FINAL STATEWIDE MODEL REVIEW PASSED"
    )

    print(
        f"Grid cells: {len(frame):,}"
    )

    print(
        f"Climate-complete cells: "
        f"{int(climate_complete.sum()):,}"
    )

    print(
        f"Eight-criterion complete cells: "
        f"{complete_count:,}"
    )

    print(
        f"Insufficient-data cells: "
        f"{incomplete_count:,}"
    )

    print(
        f"Hard-excluded cells: "
        f"{int(hard_excluded.sum()):,}"
    )

    print(
        f"Auto-screen eligible cells: "
        f"{int(auto_screen.sum()):,}"
    )

    print(
        f"Exploration-screen eligible cells: "
        f"{int(exploration_screen.sum()):,}"
    )

    print()
    print("Technical-score quantiles:")

    print(
        frame[
            "technical_suitability_score"
        ].quantile(
            [
                0.0,
                0.10,
                0.25,
                0.50,
                0.75,
                0.90,
                1.0,
            ]
        )
    )

    print()
    print("Effective-score quantiles:")

    print(
        frame[
            "effective_suitability_score"
        ].quantile(
            [
                0.0,
                0.10,
                0.25,
                0.50,
                0.75,
                0.90,
                1.0,
            ]
        )
    )

    print()
    print(
        "Candidate recommendations remain "
        "blocked pending statewide bias audit."
    )


if __name__ == "__main__":
    main()
