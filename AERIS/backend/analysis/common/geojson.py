from __future__ import annotations

from typing import Any

import geopandas as gpd

from analysis.common.io import json_scalar


def feature_collection(
    frame: gpd.GeoDataFrame,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build GeoJSON without serializing to a JSON string and parsing it again."""
    payload: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": list(
            frame.iterfeatures(
                na="null",
                show_bbox=False,
                drop_id=True,
            )
        ),
    }
    if metadata is not None:
        payload["metadata"] = json_scalar(metadata)
    return payload
