from __future__ import annotations


def normalize_linear(
    value: float,
    best: float,
    worst: float,
    higher_is_better: bool = True,
) -> float:
    """
    Normalize a raw value to a 0-1 suitability score.

    If higher_is_better=True:
      best value -> 1
      worst value -> 0

    If higher_is_better=False:
      lower values are better.
    """
    if best == worst:
        raise ValueError("best and worst cannot be the same value.")

    if higher_is_better:
        score = (value - worst) / (best - worst)
    else:
        score = (worst - value) / (worst - best)

    return round(max(0.0, min(1.0, score)), 6)