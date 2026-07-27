from __future__ import annotations

import json
from typing import Any

import requests

from analysis.decision_model import DecisionModel


class FloodHazardCriterion:
    def __init__(
        self,
        layer_url: str,
        buffer_m: float = 91.0,
    ) -> None:
        self.criterion_name = "hydro_hazard"
        self.source_layer = (
            "FEMA Effective Floodplain hosted by Maryland iMAP"
        )
        self.layer_url = layer_url.rstrip("/")
        self.buffer_m = buffer_m
        self.model = DecisionModel()

    def _query(
        self,
        lat: float,
        lon: float,
        where: str,
        distance_m: float | None = None,
    ) -> list[dict[str, Any]]:
        geometry = {
            "x": lon,
            "y": lat,
            "spatialReference": {"wkid": 4326},
        }

        data: dict[str, str] = {
            "f": "json",
            "where": where,
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": (
                "OBJECTID,DFIRM_ID,FLD_AR_ID,"
                "FLD_ZONE,ZONE_SUBTY,SFHA_TF"
            ),
            "returnGeometry": "false",
        }

        if distance_m is not None:
            data["distance"] = str(distance_m)
            data["units"] = "esriSRUnit_Meter"

        response = requests.post(
            f"{self.layer_url}/query",
            data=data,
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            raise RuntimeError(
                f"Flood service error: "
                f"{error.get('code')} - {error.get('message')}"
            )

        return payload.get("features", [])

    @staticmethod
    def _attributes(feature: dict[str, Any]) -> dict[str, Any]:
        return feature.get("attributes", {})

    def evaluate(self, lat: float, lon: float) -> dict[str, Any]:
        point_features = self._query(
            lat=lat,
            lon=lon,
            where="1=1",
        )

        nearby_sfha_features = self._query(
            lat=lat,
            lon=lon,
            where="SFHA_TF='T'",
            distance_m=self.buffer_m,
        )

        inside_sfha = any(
            str(
                self._attributes(feature).get("SFHA_TF", "")
            ).upper()
            == "T"
            for feature in point_features
        )

        within_sfha_buffer = bool(nearby_sfha_features)
        excluded = inside_sfha or within_sfha_buffer

        score = 0.0 if excluded else 1.0
        contribution = self.model.contribution(
            self.criterion_name,
            score,
        )

        flood_zones = sorted(
            {
                str(self._attributes(feature).get("FLD_ZONE"))
                for feature in point_features
                if self._attributes(feature).get("FLD_ZONE")
            }
        )

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "inside_mapped_flood_polygon": bool(point_features),
            "inside_sfha": inside_sfha,
            "within_sfha_buffer": within_sfha_buffer,
            "sfha_buffer_m": self.buffer_m,
            "flood_zones_at_point": flood_zones,
            "point_feature_count": len(point_features),
            "nearby_sfha_feature_count": len(
                nearby_sfha_features
            ),
            "excluded": excluded,
            "normalized_score": score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
        }
