from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point


MARYLAND_METERS_CRS = "EPSG:26985"


def nearest_distance_to_features_m(
    lon: float,
    lat: float,
    geojson: dict,
) -> float:
    """
    Calculate nearest distance in meters from a lon/lat point to GeoJSON features.
    """
    features = geojson.get("features", [])
    if not features:
        raise ValueError("No features provided for distance calculation.")

    point_gdf = gpd.GeoDataFrame(
        geometry=[Point(lon, lat)],
        crs="EPSG:4326",
    ).to_crs(MARYLAND_METERS_CRS)

    features_gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326").to_crs(
        MARYLAND_METERS_CRS
    )

    distances = features_gdf.distance(point_gdf.geometry.iloc[0])

    return round(float(distances.min()), 2)