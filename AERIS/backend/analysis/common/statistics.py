from __future__ import annotations

import pandas as pd


def summary_statistics(values: pd.Series) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "mean": None,
            "maximum": None,
        }
    return {
        "count": int(numeric.count()),
        "minimum": round(float(numeric.min()), 3),
        "median": round(float(numeric.median()), 3),
        "mean": round(float(numeric.mean()), 3),
        "maximum": round(float(numeric.max()), 3),
    }
