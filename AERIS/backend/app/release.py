from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
RELEASE_CONFIG_PATH = PROJECT_DIRECTORY / "configs" / "application.json"


@lru_cache(maxsize=1)
def release_metadata() -> dict[str, Any]:
    value = json.loads(RELEASE_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected release metadata object: {RELEASE_CONFIG_PATH}")
    return value
