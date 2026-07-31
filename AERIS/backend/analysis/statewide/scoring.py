from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


ScorePoint = tuple[float, float]


def validate_points(
    points: Sequence[ScorePoint],
) -> list[ScorePoint]:
    ordered = sorted(
        (
            float(x_value),
            float(score),
        )
        for x_value, score in points
    )

    if len(ordered) < 2:
        raise ValueError(
            "At least two scoring points are required."
        )

    x_values = [
        point[0]
        for point in ordered
    ]

    if len(set(x_values)) != len(x_values):
        raise ValueError(
            "Scoring-point x values must be unique."
        )

    for _, score in ordered:
        if not 0 <= score <= 1:
            raise ValueError(
                "Scoring-point values must be between 0 and 1."
            )

    return ordered


def piecewise_linear_series(
    values: pd.Series,
    points: Sequence[ScorePoint],
) -> pd.Series:
    ordered = validate_points(points)

    x_values = np.array(
        [
            point[0]
            for point in ordered
        ],
        dtype=float,
    )

    score_values = np.array(
        [
            point[1]
            for point in ordered
        ],
        dtype=float,
    )

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    result = pd.Series(
        np.nan,
        index=numeric.index,
        dtype=float,
    )

    valid = numeric.notna()

    if valid.any():
        result.loc[valid] = np.interp(
            numeric.loc[valid].to_numpy(
                dtype=float
            ),
            x_values,
            score_values,
            left=score_values[0],
            right=score_values[-1],
        )

    return result.clip(
        lower=0.0,
        upper=1.0,
    )


def inverse_distance_score_series(
    distances_m: pd.Series,
    best_m: float,
    worst_m: float,
) -> pd.Series:
    best = float(best_m)
    worst = float(worst_m)

    if worst <= best:
        raise ValueError(
            "worst_m must be greater than best_m."
        )

    distances = pd.to_numeric(
        distances_m,
        errors="coerce",
    )

    score = (
        worst - distances
    ) / (
        worst - best
    )

    return score.clip(
        lower=0.0,
        upper=1.0,
    )


def weighted_composite_series(
    components: Sequence[
        tuple[pd.Series, float]
    ],
) -> pd.Series:
    if not components:
        raise ValueError(
            "At least one component is required."
        )

    weight_total = sum(
        float(weight)
        for _, weight in components
    )

    if abs(weight_total - 1.0) > 0.000001:
        raise ValueError(
            "Component weights must total 1.0."
        )

    first_series = components[0][0]

    result = pd.Series(
        0.0,
        index=first_series.index,
        dtype=float,
    )

    complete = pd.Series(
        True,
        index=first_series.index,
        dtype=bool,
    )

    for values, weight in components:
        numeric = pd.to_numeric(
            values,
            errors="coerce",
        )

        complete &= numeric.notna()

        result += (
            numeric.fillna(0.0)
            * float(weight)
        )

    return result.where(complete)
