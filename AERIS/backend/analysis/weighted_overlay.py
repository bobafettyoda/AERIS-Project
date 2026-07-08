from __future__ import annotations

from typing import Mapping


def weighted_overlay(
    criteria_scores: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    """
    Compute weighted linear combination suitability score.

    Suitability = sum(weight_i * score_i)

    Scores should be normalized from 0 to 1.
    Weights should sum to approximately 1.
    """
    missing_scores = set(weights) - set(criteria_scores)
    if missing_scores:
        missing = ", ".join(sorted(missing_scores))
        raise ValueError(f"Missing criterion scores: {missing}")

    suitability = 0.0

    for criterion, weight in weights.items():
        score = criteria_scores[criterion]

        if not 0 <= score <= 1:
            raise ValueError(
                f"Score for '{criterion}' must be between 0 and 1. Got {score}."
            )

        suitability += weight * score

    return round(suitability, 6)