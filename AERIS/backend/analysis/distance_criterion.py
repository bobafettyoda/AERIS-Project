from __future__ import annotations

from analysis.decision_model import DecisionModel
from analysis.distance import nearest_distance_to_features_m
from analysis.normalization import normalize_linear
from connectors.arcgis import query_arcgis_geojson


class DistanceCriterion:
    def __init__(
        self,
        criterion_name: str,
        source_layer: str,
        layer_url: str,
        preferred_distance_key: str,
        search_delta_degrees: float = 0.25,
        result_record_count: int = 500,
    ) -> None:
        self.criterion_name = criterion_name
        self.source_layer = source_layer
        self.layer_url = layer_url
        self.preferred_distance_key = preferred_distance_key
        self.search_delta_degrees = search_delta_degrees
        self.result_record_count = result_record_count
        self.model = DecisionModel()

    def evaluate(self, lat: float, lon: float) -> dict:
        delta = self.search_delta_degrees
        envelope = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

        geojson = query_arcgis_geojson(
            layer_url=self.layer_url,
            where="1=1",
            result_record_count=self.result_record_count,
            geometry=envelope,
            geometry_type="esriGeometryEnvelope",
        )

        distance_m = nearest_distance_to_features_m(
            lon=lon,
            lat=lat,
            geojson=geojson,
        )

        preferred_m = self.model.preferred_distance(self.preferred_distance_key)

        score = normalize_linear(
            value=distance_m,
            best=0,
            worst=preferred_m,
            higher_is_better=False,
        )

        contribution = self.model.contribution(self.criterion_name, score)

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "input": {"lat": lat, "lon": lon},
            "search_envelope": envelope,
            "features_checked": len(geojson.get("features", [])),
            "nearest_distance_m": distance_m,
            "normalized_score": score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution["weighted_contribution"],
            "normalization": {
                "best_m": 0,
                "worst_m": preferred_m,
                "higher_is_better": False,
            },
        }