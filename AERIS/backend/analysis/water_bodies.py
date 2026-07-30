from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
import yaml
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
    """Evaluate mapped surface-water proximity and intersection."""

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

        model_path = (
            Path(__file__).resolve().parents[2]
            / "configs"
            / "decision_models"
            / "data_center_maryland_demo.yaml"
        )

        with model_path.open("r", encoding="utf-8") as file:
            model_config = yaml.safe_load(file)

        scoring = model_config.get("water_bodies_scoring")

        if not scoring:
            raise RuntimeError(
                "water_bodies_scoring is missing from "
                "the decision-model YAML."
            )

        self.methodology = scoring["method"]

        self.inside_waterbody_exclusion = bool(
            scoring["inside_waterbody_exclusion"]
        )

        self.beyond_search_radius_score = float(
            scoring["beyond_search_radius_score"]
        )

        self.distance_points = [
            (
                float(point["distance_m"]),
                float(point["score"]),
            )
            for point in scoring["distance_points"]
        ]

        self.distance_points.sort(
            key=lambda point: point[0]
        )

        if len(self.distance_points) < 2:
            raise RuntimeError(
                "Water scoring requires at least "
                "two distance points."
            )

        self.limitations = list(
            scoring.get("limitations", [])
        )

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
                f"Waterbody service error on layer "
                f"{layer_id}: {error.get('code')} - "
                f"{error.get('message')}"
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

            distances.append(
                float(point.distance(geometry))
            )

        if not distances:
            return None

        return round(min(distances), 2)

    def _interpolate_score(
        self,
        distance_m: float,
    ) -> float:
        first_distance, first_score = (
            self.distance_points[0]
        )

        if distance_m <= first_distance:
            return round(first_score, 6)

        for index in range(
            1,
            len(self.distance_points),
        ):
            lower_distance, lower_score = (
                self.distance_points[index - 1]
            )
            upper_distance, upper_score = (
                self.distance_points[index]
            )

            if distance_m <= upper_distance:
                interval = (
                    upper_distance - lower_distance
                )

                if interval == 0:
                    return round(upper_score, 6)

                fraction = (
                    distance_m - lower_distance
                ) / interval

                score = lower_score + fraction * (
                    upper_score - lower_score
                )

                return round(
                    max(0.0, min(1.0, score)),
                    6,
                )

        return round(
            self.beyond_search_radius_score,
            6,
        )

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        results: dict[str, dict[str, Any]] = {}

        inside_waterbody = False
        inside_categories: list[str] = []

        for category, config in (
            WATERBODY_LAYERS.items()
        ):
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
                "nearby_feature_count": len(
                    nearby_features
                ),
                "nearest_distance_m": (
                    self._nearest_distance_m(
                        lat=lat,
                        lon=lon,
                        features=nearby_features,
                    )
                ),
            }

        nearest_distances = [
            result["nearest_distance_m"]
            for result in results.values()
            if result["nearest_distance_m"]
            is not None
        ]

        nearest_surface_water_m = (
            min(nearest_distances)
            if nearest_distances
            else None
        )

        excluded = (
            inside_waterbody
            and self.inside_waterbody_exclusion
        )

        if excluded:
            score = 0.0
            scoring_basis = (
                "inside_mapped_waterbody"
            )
        elif nearest_surface_water_m is None:
            score = self.beyond_search_radius_score
            scoring_basis = (
                "no_mapped_water_within_search_radius"
            )
        else:
            score = self._interpolate_score(
                nearest_surface_water_m
            )
            scoring_basis = (
                "nearest_mapped_stream_or_lake"
            )

        contribution = self.model.contribution(
            self.criterion_name,
            score,
        )

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "methodology": self.methodology,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "search_radius_m": self.search_radius_m,
            "inside_waterbody": inside_waterbody,
            "inside_categories": inside_categories,
            "nearest_surface_water_m": (
                nearest_surface_water_m
            ),
            "nearest_stream_m": results["stream"][
                "nearest_distance_m"
            ],
            "nearest_lake_m": results["lake"][
                "nearest_distance_m"
            ],
            "stream_features_checked": (
                results["stream"][
                    "nearby_feature_count"
                ]
            ),
            "lake_features_checked": (
                results["lake"][
                    "nearby_feature_count"
                ]
            ),
            "scoring_basis": scoring_basis,
            "excluded": excluded,
            "scoring_status": "scored",
            "normalized_score": score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
            "normalization": {
                "distance_basis": (
                    "nearest_of_stream_or_lake"
                ),
                "distance_points": [
                    {
                        "distance_m": distance,
                        "score": point_score,
                    }
                    for distance, point_score
                    in self.distance_points
                ],
                "beyond_search_radius_score": (
                    self.beyond_search_radius_score
                ),
            },
            "layers": results,
            "limitations": self.limitations,
        }
