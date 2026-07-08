from fastapi import APIRouter

from connectors.arcgis import (
    count_arcgis_features,
    query_arcgis_geojson,
    query_arcgis_geojson_paged,
)

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