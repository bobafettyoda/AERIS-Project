from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

import pandas as pd


TECHNICAL_CRITERIA = (
    "climate",
    "grid_infrastructure",
    "telecom_infrastructure",
    "protected_areas",
    "water_bodies",
    "population_density",
    "road_access",
    "hydro_hazard",
)


SelectionMode = Literal[
    "auto",
    "exploration",
]


def normalize_weights(
    weights: Mapping[str, float],
    criteria: Sequence[str] = (
        TECHNICAL_CRITERIA
    ),
) -> dict[str, float]:
    unknown = set(weights) - set(criteria)

    if unknown:
        raise ValueError(
            "Unknown criteria in weights: "
            + ", ".join(sorted(unknown))
        )

    normalized_input: dict[
        str,
        float,
    ] = {}

    for criterion in criteria:
        value = float(
            weights.get(criterion, 0.0)
        )

        if value < 0:
            raise ValueError(
                f"Weight for {criterion} "
                "cannot be negative."
            )

        normalized_input[criterion] = value

    total = sum(
        normalized_input.values()
    )

    if total <= 0:
        raise ValueError(
            "At least one criterion must "
            "have a positive weight."
        )

    return {
        criterion: value / total
        for criterion, value
        in normalized_input.items()
    }


class ScenarioEngine:
    """
    Apply custom technical weights without using
    demographic attributes in the score.
    """

    def __init__(
        self,
        criteria: Sequence[str] = (
            TECHNICAL_CRITERIA
        ),
    ) -> None:
        self.criteria = tuple(criteria)

    def score_cells(
        self,
        cells: pd.DataFrame,
        weights: Mapping[str, float],
    ) -> pd.DataFrame:
        missing = [
            criterion
            for criterion in self.criteria
            if criterion not in cells.columns
        ]

        if missing:
            raise ValueError(
                "Cell data is missing technical "
                "criteria: "
                + ", ".join(missing)
            )

        result = cells.copy()

        normalized_weights = (
            normalize_weights(
                weights=weights,
                criteria=self.criteria,
            )
        )

        complete = pd.Series(
            True,
            index=result.index,
            dtype=bool,
        )

        technical_score = pd.Series(
            0.0,
            index=result.index,
            dtype=float,
        )

        for criterion in self.criteria:
            values = pd.to_numeric(
                result[criterion],
                errors="coerce",
            )

            invalid = (
                values.notna()
                & (
                    (values < 0)
                    | (values > 1)
                )
            )

            if invalid.any():
                sample_cells = (
                    result.loc[
                        invalid,
                        "cell_id",
                    ].astype(str)
                    if "cell_id"
                    in result.columns
                    else result.index[
                        invalid
                    ].astype(str)
                )

                raise ValueError(
                    f"{criterion} contains scores "
                    "outside 0-1 for cells: "
                    + ", ".join(
                        sample_cells[:5]
                    )
                )

            complete &= values.notna()

            technical_score += (
                values.fillna(0.0)
                * normalized_weights[
                    criterion
                ]
            )

        result[
            "technical_score_complete"
        ] = complete

        result["technical_score"] = (
            technical_score.where(
                complete
            )
        )

        if "hard_excluded" in result:
            hard_excluded = (
                result["hard_excluded"]
                .fillna(True)
                .astype(bool)
            )
        else:
            hard_excluded = pd.Series(
                False,
                index=result.index,
                dtype=bool,
            )

        if "equity_gate" in result:
            equity_gate = (
                result["equity_gate"]
                .fillna(
                    "INSUFFICIENT_DATA"
                )
                .astype(str)
            )
        else:
            equity_gate = pd.Series(
                "INSUFFICIENT_DATA",
                index=result.index,
                dtype=str,
            )

        result["hard_excluded"] = (
            hard_excluded
        )

        result["equity_gate"] = (
            equity_gate
        )

        result[
            "auto_recommendation_eligible"
        ] = (
            complete
            & ~hard_excluded
            & equity_gate.eq("PASS")
        )

        result[
            "exploration_eligible"
        ] = (
            complete
            & ~hard_excluded
            & equity_gate.isin(
                ["PASS", "CAUTION"]
            )
        )

        result.attrs[
            "normalized_weights"
        ] = normalized_weights

        return result

    @staticmethod
    def filter_score_band(
        scored_cells: pd.DataFrame,
        minimum: float,
        maximum: float,
        mode: SelectionMode = (
            "exploration"
        ),
    ) -> pd.DataFrame:
        if not 0 <= minimum <= 1:
            raise ValueError(
                "minimum must be between "
                "0 and 1."
            )

        if not 0 <= maximum <= 1:
            raise ValueError(
                "maximum must be between "
                "0 and 1."
            )

        if minimum > maximum:
            raise ValueError(
                "minimum cannot exceed "
                "maximum."
            )

        eligibility_column = (
            "auto_recommendation_eligible"
            if mode == "auto"
            else "exploration_eligible"
        )

        required = {
            "technical_score",
            eligibility_column,
        }

        missing = required - set(
            scored_cells.columns
        )

        if missing:
            raise ValueError(
                "Scored cell data is missing: "
                + ", ".join(sorted(missing))
            )

        mask = (
            scored_cells[
                eligibility_column
            ].astype(bool)
            & scored_cells[
                "technical_score"
            ].between(
                minimum,
                maximum,
                inclusive="both",
            )
        )

        return (
            scored_cells.loc[mask]
            .sort_values(
                "technical_score",
                ascending=False,
            )
            .reset_index(drop=True)
        )

    @staticmethod
    def select_top_n(
        scored_cells: pd.DataFrame,
        count: int = 5,
        minimum_spacing_m: float = (
            10000
        ),
        mode: SelectionMode = "auto",
    ) -> pd.DataFrame:
        if count <= 0:
            raise ValueError(
                "count must be positive."
            )

        if minimum_spacing_m < 0:
            raise ValueError(
                "minimum_spacing_m cannot "
                "be negative."
            )

        eligibility_column = (
            "auto_recommendation_eligible"
            if mode == "auto"
            else "exploration_eligible"
        )

        required = {
            "technical_score",
            "analysis_x_m",
            "analysis_y_m",
            eligibility_column,
        }

        missing = required - set(
            scored_cells.columns
        )

        if missing:
            raise ValueError(
                "Scored cell data is missing: "
                + ", ".join(sorted(missing))
            )

        candidates = (
            scored_cells.loc[
                scored_cells[
                    eligibility_column
                ].astype(bool)
                & scored_cells[
                    "technical_score"
                ].notna()
            ]
            .sort_values(
                "technical_score",
                ascending=False,
            )
        )

        selected_indices: list[
            object
        ] = []

        selected_coordinates: list[
            tuple[float, float]
        ] = []

        for index, row in (
            candidates.iterrows()
        ):
            x_value = float(
                row["analysis_x_m"]
            )

            y_value = float(
                row["analysis_y_m"]
            )

            far_enough = all(
                math.hypot(
                    x_value - selected_x,
                    y_value - selected_y,
                )
                >= minimum_spacing_m
                for (
                    selected_x,
                    selected_y,
                )
                in selected_coordinates
            )

            if not far_enough:
                continue

            selected_indices.append(index)

            selected_coordinates.append(
                (x_value, y_value)
            )

            if (
                len(selected_indices)
                >= count
            ):
                break

        return (
            candidates.loc[
                selected_indices
            ]
            .reset_index(drop=True)
        )
