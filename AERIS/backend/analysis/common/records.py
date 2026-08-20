from __future__ import annotations

from typing import Any

import pandas as pd


def record_value(record: pd.Series, column: str) -> Any:
    if column not in record.index:
        return None
    result = record[column]
    try:
        if pd.isna(result):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(result, "item"):
        try:
            return result.item()
        except (TypeError, ValueError):
            pass
    return result
