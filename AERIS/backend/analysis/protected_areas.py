from __future__ import annotations

import json
from typing import Any

import requests

from analysis.decision_model import DecisionModel


PROTECTED_LAND_LAYERS = {
    0: "DNR-owned lands and conservation easements",
    1: "Rural Legacy properties",
    2: "Maryland Environmental Trust easements",
    3: "Forest Conservation Act easements",
    4: "Agricultural preservation easements",
    5: "Local protected lands",
    6: "Coastal and estuarine conservation lands",
    7: "Private conservation lands",
    8: "Protected federal lands",
    9: "Transfer and Purchase of Development Rights",
}


class ProtectedAreasCriterion:
    def __init__(self, service_url: str) -> None:
        self.criterion_name = "protected_areas"
        self.source_layer = "Maryland Protected Lands"
        self.service_url = service_url.rstrip("/")
        self.model = DecisionModel()

    def _query_layer(
        self,
        layer_id: int,
        lat: float,
        lon: float,
    ) -> int:
        geometry = {
            "x": lon,
            "y": lat,
            "spatialReference": {"wkid": 4326},
        }

        data = {
            "f": "json",
            "where": "1=1",
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "returnCountOnly": "true",
        }

        response = requests.post(
            f"{self.service_url}/{layer_id}/query",
            data=data,
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload: dict[str, Any] = response.json()

        if "error" in payload:
            error = payload["error"]
            raise RuntimeError(
                f"Protected-lands service error on layer "
                f"{layer_id}: {error.get('code')} - "
                f"{error.get('message')}"
            )

        return int(payload.get("count", 0))

    def evaluate(self, lat: float, lon: float) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []

        for layer_id, layer_name in PROTECTED_LAND_LAYERS.items():
            count = self._query_layer(
                layer_id=layer_id,
                lat=lat,
                lon=lon,
            )

            if count > 0:
                matches.append(
                    {
                        "layer_id": layer_id,
                        "layer_name": layer_name,
                        "feature_count": count,
                    }
                )

        inside_protected_area = bool(matches)
        excluded = inside_protected_area
        score = 0.0 if excluded else 1.0

        contribution = self.model.contribution(
            self.criterion_name,
            score,
        )

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "layers_checked": len(PROTECTED_LAND_LAYERS),
            "inside_protected_area": inside_protected_area,
            "matched_layer_count": len(matches),
            "matches": matches,
            "excluded": excluded,
            "normalized_score": score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
        }
