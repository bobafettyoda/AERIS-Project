from fastapi import APIRouter

from connectors.arcgis import (
    count_arcgis_features,
    query_arcgis_geojson,
    query_arcgis_geojson_paged,
)
from analysis.distance import nearest_distance_to_features_m
from analysis.normalization import normalize_linear

router = APIRouter(prefix="/gis", tags=["gis"])

ROADS_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlinesComprehensive/MapServer/0"
)


@router.get("/roads/prince-georges")
def get_prince_georges_roads():
    geojson = query_arcgis_geojson(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
        result_record_count=1,
    )

    return {
        "study_area": "Prince George's County",
        "county_code": 16,
        "feature_count": len(geojson.get("features", [])),
        "geojson": geojson,
    }
@router.get("/roads/prince-georges/count")
def count_prince_georges_roads():
    count = count_arcgis_features(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
    )

    return {
        "study_area": "Prince George's County",
        "county_code": 16,
        "feature_count": count,
    }
@router.get("/roads/prince-georges/page")
def get_prince_georges_roads_page(offset: int = 0, limit: int = 100):
    geojson = query_arcgis_geojson(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
        result_record_count=limit,
        result_offset=offset,
    )

    return {
        "study_area": "Prince George's County",
        "county_code": 16,
        "offset": offset,
        "limit": limit,
        "feature_count": len(geojson.get("features", [])),
        "geojson": geojson,
    }
@router.get("/roads/prince-georges/paged-sample")
def get_prince_georges_roads_paged_sample(max_features: int = 25):
    geojson = query_arcgis_geojson_paged(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
        page_size=10,
        max_features=max_features,
    )

    return {
        "study_area": "Prince George's County",
        "county_code": 16,
        "feature_count": len(geojson.get("features", [])),
        "geojson": geojson,
    }
@router.get("/roads/prince-georges/access-score")
def get_prince_georges_road_access_score(lat: float, lon: float):
    roads_geojson = query_arcgis_geojson_paged(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
        page_size=500,
        max_features=5000,
    )

    distance_m = nearest_distance_to_features_m(
        lon=lon,
        lat=lat,
        geojson=roads_geojson,
    )

    score = normalize_linear(
        value=distance_m,
        best=800,
        worst=5000,
        higher_is_better=False,
    )

    return {
        "criterion": "road_access",
        "study_area": "Prince George's County",
        "input": {
            "lat": lat,
            "lon": lon,
        },
        "nearest_road_distance_m": distance_m,
        "score": score,
        "normalization": {
            "best_m": 800,
            "worst_m": 5000,
            "higher_is_better": False,
        },
    }
@router.get("/roads/prince-georges/access-score-with-overlay")
def get_road_access_score_with_overlay(lat: float, lon: float):
    roads_geojson = query_arcgis_geojson_paged(
        layer_url=ROADS_LAYER_URL,
        where="COUNTY=16",
        page_size=500,
        max_features=5000,
    )

    distance_m = nearest_distance_to_features_m(
        lon=lon,
        lat=lat,
        geojson=roads_geojson,
    )

    road_score = normalize_linear(
        value=distance_m,
        best=800,
        worst=5000,
        higher_is_better=False,
    )

    return {
        "criterion": "road_access",
        "study_area": "Prince George's County",
        "input": {"lat": lat, "lon": lon},
        "nearest_road_distance_m": distance_m,
        "road_access_score": road_score,
        "weighted_contribution": round(road_score * 0.0795, 6),
        "road_access_weight": 0.0795,
    }