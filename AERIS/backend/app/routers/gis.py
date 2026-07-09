from fastapi import APIRouter

from connectors.arcgis import (
    count_arcgis_features,
    query_arcgis_geojson,
    query_arcgis_geojson_paged,
)
from analysis.distance import nearest_distance_to_features_m
from analysis.normalization import normalize_linear
from analysis.decision_model import DecisionModel

router = APIRouter(prefix="/gis", tags=["gis"])

ROADS_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlinesComprehensive/MapServer/0"
)

TRANSMISSION_LINES_LAYER_URL = (
    "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/"
    "HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0"
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

    model = DecisionModel()
    contribution = model.contribution("road_access", road_score)

    return {
        "criterion": "road_access",
        "study_area": "Prince George's County",
        "input": {"lat": lat, "lon": lon},
        "nearest_road_distance_m": distance_m,
        "road_access_score": road_score,
        "road_access_weight": contribution["weight"],
        "weighted_contribution": contribution["weighted_contribution"],
    }
@router.get("/power/transmission/access-score")
def get_transmission_access_score(lat: float, lon: float):
    # Rough bounding box around candidate point.
    # 0.25 degrees is roughly 15-20 miles in Maryland.
    delta = 0.25
    envelope = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

    lines_geojson = query_arcgis_geojson(
        layer_url=TRANSMISSION_LINES_LAYER_URL,
        where="1=1",
        result_record_count=500,
        geometry=envelope,
        geometry_type="esriGeometryEnvelope",
    )

    distance_m = nearest_distance_to_features_m(
        lon=lon,
        lat=lat,
        geojson=lines_geojson,
    )

    model = DecisionModel()
    preferred_m = model.preferred_distance("transmission_line_m")

    score = normalize_linear(
        value=distance_m,
        best=0,
        worst=preferred_m,
        higher_is_better=False,
    )

    contribution = model.contribution("grid_infrastructure", score)

    return {
        "criterion": "grid_infrastructure",
        "source_layer": "HIFLD Electric Power Transmission Lines",
        "input": {"lat": lat, "lon": lon},
        "search_envelope": envelope,
        "features_checked": len(lines_geojson.get("features", [])),
        "nearest_transmission_line_distance_m": distance_m,
        "normalized_score": score,
        "weight": contribution["weight"],
        "weighted_contribution": contribution["weighted_contribution"],
        "normalization": {
            "best_m": 0,
            "worst_m": preferred_m,
            "higher_is_better": False,
        },
    }