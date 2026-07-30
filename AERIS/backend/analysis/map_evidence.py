from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import (
    LineString,
    Point,
    mapping,
    shape,
)
from shapely.ops import nearest_points, transform


FeatureCollection = dict[str, Any]


def empty_feature_collection() -> FeatureCollection:
    return {
        "type": "FeatureCollection",
        "features": [],
    }


class SiteMapEvidence:
    """
    Return nearby GIS context and the specific mapped
    features nearest to an evaluated candidate point.
    """

    def __init__(
        self,
        roads_layer_url: str,
        transmission_layer_url: str,
        substation_layer_url: str,
        floodplain_layer_url: str,
        protected_lands_service_url: str,
        waterbodies_service_url: str,
        search_radius_m: float = 5000.0,
    ) -> None:
        self.roads_layer_url = (
            roads_layer_url.rstrip("/")
        )
        self.transmission_layer_url = (
            transmission_layer_url.rstrip("/")
        )
        self.substation_layer_url = (
            substation_layer_url.rstrip("/")
        )
        self.floodplain_layer_url = (
            floodplain_layer_url.rstrip("/")
        )
        self.protected_lands_service_url = (
            protected_lands_service_url.rstrip("/")
        )
        self.waterbodies_service_url = (
            waterbodies_service_url.rstrip("/")
        )
        self.search_radius_m = search_radius_m

        self.to_maryland = Transformer.from_crs(
            "EPSG:4326",
            "EPSG:26985",
            always_xy=True,
        ).transform

        self.to_wgs84 = Transformer.from_crs(
            "EPSG:26985",
            "EPSG:4326",
            always_xy=True,
        ).transform

    @staticmethod
    def _trim_properties(
        properties: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not properties:
            return {}

        preferred_fields = {
            "OBJECTID",
            "ObjectID",
            "FID",
            "NAME",
            "Name",
            "FACILITY",
            "SUB_NAME",
            "SUBNAME",
            "VOLTAGE",
            "OWNER",
            "OWNER_NAME",
            "ROADNAMESHA",
            "ROAD_NAME",
            "ROUTEID",
            "ID_PREFIX",
            "ID_RTE_NO",
            "FLD_ZONE",
            "ZONE_SUBTY",
            "SFHA_TF",
            "COUNTY",
            "_source_layer_id",
        }

        trimmed = {
            key: value
            for key, value in properties.items()
            if key in preferred_fields
        }

        if trimmed:
            return trimmed

        return dict(
            list(properties.items())[:8]
        )

    def _query_geojson(
        self,
        layer_url: str,
        lat: float,
        lon: float,
        distance_m: float,
        max_features: int,
        where: str = "1=1",
    ) -> FeatureCollection:
        point_geometry = {
            "x": lon,
            "y": lat,
            "spatialReference": {
                "wkid": 4326,
            },
        }

        response = requests.post(
            f"{layer_url}/query",
            data={
                "f": "geojson",
                "where": where,
                "geometry": json.dumps(
                    point_geometry
                ),
                "geometryType": (
                    "esriGeometryPoint"
                ),
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": (
                    "esriSpatialRelIntersects"
                ),
                "distance": str(distance_m),
                "units": "esriSRUnit_Meter",
                "outFields": "*",
                "returnGeometry": "true",
                "resultRecordCount": str(
                    max_features
                ),
            },
            headers={
                "User-Agent": "AERIS/0.1",
            },
            timeout=90,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]

            raise RuntimeError(
                "ArcGIS evidence service error: "
                f"{error.get('code')} - "
                f"{error.get('message')}"
            )

        if payload.get("type") != (
            "FeatureCollection"
        ):
            return empty_feature_collection()

        return payload

    def _prepare_feature(
        self,
        feature: dict[str, Any],
        simplify_tolerance_m: float = 6.0,
    ) -> dict[str, Any] | None:
        geometry_data = feature.get("geometry")

        if not geometry_data:
            return None

        try:
            geometry_wgs84 = shape(
                geometry_data
            )

            geometry_maryland = transform(
                self.to_maryland,
                geometry_wgs84,
            )

            if geometry_maryland.geom_type not in {
                "Point",
                "MultiPoint",
            }:
                geometry_maryland = (
                    geometry_maryland.simplify(
                        simplify_tolerance_m,
                        preserve_topology=True,
                    )
                )

            prepared_geometry = transform(
                self.to_wgs84,
                geometry_maryland,
            )
        except Exception:
            prepared_geometry = shape(
                geometry_data
            )

        return {
            "type": "Feature",
            "geometry": mapping(
                prepared_geometry
            ),
            "properties": self._trim_properties(
                feature.get("properties")
            ),
        }

    def _prepare_collection(
        self,
        collection: FeatureCollection,
        simplify_tolerance_m: float = 6.0,
    ) -> FeatureCollection:
        prepared_features = []

        for feature in collection.get(
            "features",
            [],
        ):
            prepared = self._prepare_feature(
                feature,
                simplify_tolerance_m=(
                    simplify_tolerance_m
                ),
            )

            if prepared:
                prepared_features.append(prepared)

        return {
            "type": "FeatureCollection",
            "features": prepared_features,
        }

    def _nearest_feature(
        self,
        collection: FeatureCollection,
        lat: float,
        lon: float,
    ) -> tuple[
        dict[str, Any] | None,
        float | None,
        Point | None,
    ]:
        candidate_wgs84 = Point(lon, lat)
        candidate_maryland = transform(
            self.to_maryland,
            candidate_wgs84,
        )

        nearest_feature = None
        nearest_distance = None
        nearest_location = None

        for feature in collection.get(
            "features",
            [],
        ):
            geometry_data = feature.get(
                "geometry"
            )

            if not geometry_data:
                continue

            try:
                feature_wgs84 = shape(
                    geometry_data
                )

                feature_maryland = transform(
                    self.to_maryland,
                    feature_wgs84,
                )

                distance = float(
                    candidate_maryland.distance(
                        feature_maryland
                    )
                )

                if (
                    nearest_distance is None
                    or distance < nearest_distance
                ):
                    _, location_maryland = (
                        nearest_points(
                            candidate_maryland,
                            feature_maryland,
                        )
                    )

                    location_wgs84 = transform(
                        self.to_wgs84,
                        location_maryland,
                    )

                    nearest_feature = feature
                    nearest_distance = distance
                    nearest_location = (
                        location_wgs84
                    )
            except Exception:
                continue

        return (
            nearest_feature,
            nearest_distance,
            nearest_location,
        )

    @staticmethod
    def _connector_collection(
        lat: float,
        lon: float,
        nearest_location: Point | None,
    ) -> FeatureCollection:
        if nearest_location is None:
            return empty_feature_collection()

        connector = LineString(
            [
                (lon, lat),
                (
                    nearest_location.x,
                    nearest_location.y,
                ),
            ]
        )

        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": mapping(
                        connector
                    ),
                    "properties": {
                        "role": "distance_connector",
                    },
                }
            ],
        }

    def _nearest_search_collection(
        self,
        layer_url: str,
        lat: float,
        lon: float,
        where: str = "1=1",
    ) -> FeatureCollection:
        search_steps = [
            250.0,
            500.0,
            1000.0,
            2000.0,
            4000.0,
            self.search_radius_m,
        ]

        for radius_m in sorted(
            set(search_steps)
        ):
            collection = self._query_geojson(
                layer_url=layer_url,
                lat=lat,
                lon=lon,
                distance_m=radius_m,
                max_features=1500,
                where=where,
            )

            if collection.get("features"):
                return collection

        return empty_feature_collection()

    def _nearest_bundle(
        self,
        layer_url: str,
        lat: float,
        lon: float,
        context_limit: int,
        where: str = "1=1",
    ) -> dict[str, Any]:
        nearest_search = (
            self._nearest_search_collection(
                layer_url=layer_url,
                lat=lat,
                lon=lon,
                where=where,
            )
        )

        (
            nearest_feature,
            nearest_distance,
            nearest_location,
        ) = self._nearest_feature(
            collection=nearest_search,
            lat=lat,
            lon=lon,
        )

        context_collection = (
            self._query_geojson(
                layer_url=layer_url,
                lat=lat,
                lon=lon,
                distance_m=self.search_radius_m,
                max_features=context_limit,
                where=where,
            )
        )

        if nearest_feature is None:
            nearest_collection = (
                empty_feature_collection()
            )
        else:
            prepared_nearest = (
                self._prepare_feature(
                    nearest_feature,
                    simplify_tolerance_m=2.0,
                )
            )

            nearest_collection = {
                "type": "FeatureCollection",
                "features": (
                    [prepared_nearest]
                    if prepared_nearest
                    else []
                ),
            }

        return {
            "status": "ok",
            "distance_m": (
                round(nearest_distance, 2)
                if nearest_distance
                is not None
                else None
            ),
            "nearby": self._prepare_collection(
                context_collection
            ),
            "nearest": nearest_collection,
            "connector": (
                self._connector_collection(
                    lat=lat,
                    lon=lon,
                    nearest_location=(
                        nearest_location
                    ),
                )
            ),
        }

    def _context_bundle(
        self,
        layer_url: str,
        lat: float,
        lon: float,
        context_limit: int,
        where: str = "1=1",
    ) -> dict[str, Any]:
        collection = self._query_geojson(
            layer_url=layer_url,
            lat=lat,
            lon=lon,
            distance_m=self.search_radius_m,
            max_features=context_limit,
            where=where,
        )

        return {
            "status": "ok",
            "nearby": self._prepare_collection(
                collection
            ),
        }

    def _protected_bundle(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        combined_features = []
        layer_errors = []

        for layer_id in range(10):
            layer_url = (
                f"{self.protected_lands_service_url}"
                f"/{layer_id}"
            )

            try:
                collection = (
                    self._query_geojson(
                        layer_url=layer_url,
                        lat=lat,
                        lon=lon,
                        distance_m=(
                            self.search_radius_m
                        ),
                        max_features=75,
                    )
                )
            except Exception as error:
                layer_errors.append(
                    {
                        "layer_id": layer_id,
                        "error": str(error),
                    }
                )
                continue

            for feature in collection.get(
                "features",
                [],
            ):
                properties = dict(
                    feature.get(
                        "properties",
                        {},
                    )
                )

                properties[
                    "_source_layer_id"
                ] = layer_id

                feature = dict(feature)
                feature["properties"] = (
                    properties
                )

                combined_features.append(
                    feature
                )

        combined = {
            "type": "FeatureCollection",
            "features": combined_features,
        }

        return {
            "status": "ok",
            "nearby": self._prepare_collection(
                combined,
                simplify_tolerance_m=10.0,
            ),
            "layer_errors": layer_errors,
        }

    @staticmethod
    def _safe(
        function: Callable[
            [],
            dict[str, Any],
        ],
    ) -> dict[str, Any]:
        try:
            return function()
        except Exception as error:
            return {
                "status": "error",
                "error_type": (
                    type(error).__name__
                ),
                "error": str(error),
                "nearby": (
                    empty_feature_collection()
                ),
                "nearest": (
                    empty_feature_collection()
                ),
                "connector": (
                    empty_feature_collection()
                ),
                "distance_m": None,
            }

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        stream_url = (
            f"{self.waterbodies_service_url}/2"
        )
        lake_url = (
            f"{self.waterbodies_service_url}/3"
        )

        layers = {
            "road": self._safe(
                lambda: self._nearest_bundle(
                    layer_url=(
                        self.roads_layer_url
                    ),
                    lat=lat,
                    lon=lon,
                    context_limit=300,
                )
            ),
            "transmission": self._safe(
                lambda: self._nearest_bundle(
                    layer_url=(
                        self.transmission_layer_url
                    ),
                    lat=lat,
                    lon=lon,
                    context_limit=200,
                )
            ),
            "substation": self._safe(
                lambda: self._nearest_bundle(
                    layer_url=(
                        self.substation_layer_url
                    ),
                    lat=lat,
                    lon=lon,
                    context_limit=100,
                )
            ),
            "stream": self._safe(
                lambda: self._nearest_bundle(
                    layer_url=stream_url,
                    lat=lat,
                    lon=lon,
                    context_limit=250,
                )
            ),
            "lake": self._safe(
                lambda: self._nearest_bundle(
                    layer_url=lake_url,
                    lat=lat,
                    lon=lon,
                    context_limit=100,
                )
            ),
            "flood": self._safe(
                lambda: self._context_bundle(
                    layer_url=(
                        self.floodplain_layer_url
                    ),
                    lat=lat,
                    lon=lon,
                    context_limit=200,
                )
            ),
            "protected": self._safe(
                lambda: self._protected_bundle(
                    lat=lat,
                    lon=lon,
                )
            ),
        }

        return {
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "search_radius_m": (
                self.search_radius_m
            ),
            "layers": layers,
            "interpretation": {
                "nearby": (
                    "Mapped features returned within "
                    "the evidence search radius."
                ),
                "nearest": (
                    "The mapped feature nearest to "
                    "the selected candidate point."
                ),
                "connector": (
                    "A display line between the "
                    "candidate point and nearest "
                    "location on that feature."
                ),
            },
        }
