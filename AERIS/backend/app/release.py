from __future__ import annotations

import json
import os
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


def runtime_release_metadata() -> dict[str, str | None]:
    """Deployment/data identifiers injected by the release system.

    These values deliberately live outside application.json so a code release can be
    promoted or rolled back without rewriting analytical source metadata.
    """

    return {
        "deployment_release_id": os.getenv("AERIS_DEPLOYMENT_RELEASE_ID") or None,
        "data_snapshot_id": os.getenv("AERIS_DATA_SNAPSHOT_ID") or None,
        "data_manifest_sha256": os.getenv("AERIS_DATA_MANIFEST_SHA256") or None,
    }
