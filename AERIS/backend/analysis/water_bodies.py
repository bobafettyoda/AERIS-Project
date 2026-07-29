from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import requests
from shapely.geometry import Point, shape

from analysis.decision_model import DecisionModel


WATERBODY_LAYERS = {
    "stream": {
        "layer_id": 2,
        "label": "Detailed rivers and streams",
    },
    "lake": {
        "layer_id": 3,
        "label": "Detailed lakes",
    },
}


class WaterBodiesCriterion:
    def __init__(
        self,
        service_url: str,
        search_radius_m: float = 5000.0,
    ) -> None:
        self.criterion_name = "water_bodies"
        self.source_layer = "Maryland Waterbodies"
        self.service_url = service_url.rstrip("/")
        self.search_radius_m = search_radius_m
        self.model = DecisionModel()

    def _query_layer(
        self,
        layer_id: int,
        lat: float,
        lon: float,
        distance_m: float | None = None,
        return_geometry: bool = True,
    ) -> list[dict[str, Any]]:
        geometry = {
            "x": lon,
            "y": lat,
            "spatialReference": {"wkid": 4326},
        }

        data: dict[str, str] = {
            "f": "geojson",
            "where": "1=1",
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": str(return_geometry).lower(),
        }

        if distance_m is not None:
            data["distance"] = str(distance_m)
            data["units"] = "esriSRUnit_Meter"

        response = requests.post(
            f"{self.service_url}/{layer_id}/query",
            data=data,
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            raise RuntimeError(
                f"Waterbody service error on layer {layer_id}: "
                f"{error.get('code')} - {error.get('message')}"
            )

        return payload.get("features", [])

    @staticmethod
    def _nearest_distance_m(
        lat: float,
        lon: float,
        features: list[dict[str, Any]],
    ) -> float | None:
        if not features:
            return None

        point = gpd.GeoSeries(
            [Point(lon, lat)],
            crs="EPSG:4326",
        ).to_crs("EPSG:26985").iloc[0]

        distances: list[float] = []

        for feature in features:
            geometry_data = feature.get("geometry")
            if not geometry_data:
                continue

            geometry = gpd.GeoSeries(
                [shape(geometry_data)],
                crs="EPSG:4326",
            ).to_crs("EPSG:26985").iloc[0]

            distances.append(point.distance(geometry))

        if not distances:
            return None

        return round(min(distances), 2)

    def evaluate(self, lat: float, lon: float) -> dict[str, Any]:
        results: dict[str, dict[str, Any]] = {}

        inside_waterbody = False
        inside_categories: list[str] = []

        for category, config in WATERBODY_LAYERS.items():
            layer_id = config["layer_id"]

            direct_features = self._query_layer(
                layer_id=layer_id,
                lat=lat,
                lon=lon,
                distance_m=None,
                return_geometry=False,
            )

            nearby_features = self._query_layer(
                layer_id=layer_id,
                lat=lat,
                lon=lon,
                distance_m=self.search_radius_m,
                return_geometry=True,
            )

            intersects = bool(direct_features)

            if intersects:
                inside_waterbody = True
                inside_categories.append(category)

            results[category] = {
                "layer_id": layer_id,
                "layer_name": config["label"],
                "intersects": intersects,
                "nearby_feature_count": len(nearby_features),
                "nearest_distance_m": self._nearest_distance_m(
                    lat=lat,
                    lon=lon,
                    features=nearby_features,
                ),
            }

        excluded = inside_waterbody

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "search_radius_m": self.search_radius_m,
            "inside_waterbody": inside_waterbody,
            "inside_categories": inside_categories,
            "nearest_stream_m": results["stream"][
                "nearest_distance_m"
            ],
            "nearest_lake_m": results["lake"][
                "nearest_distance_m"
            ],
            "stream_features_checked": results["stream"][
                "nearby_feature_count"
            ],
            "lake_features_checked": results["lake"][
                "nearby_feature_count"
            ],
            "excluded": excluded,
            "scoring_status": "pending_methodology",
            "normalized_score": None,
            "weight": self.model.weight(self.criterion_name),
            "weighted_contribution": None,
            "layers": results,
        }
