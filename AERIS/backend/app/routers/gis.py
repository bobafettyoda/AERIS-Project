from analysis.telecom_infrastructure import TelecomInfrastructureCriterion
from fastapi import APIRouter

from connectors.arcgis import (
    count_arcgis_features,
    query_arcgis_geojson,
    query_arcgis_geojson_paged,
)
from analysis.distance_criterion import DistanceCriterion
from analysis.flood_hazard import FloodHazardCriterion
from analysis.protected_areas import ProtectedAreasCriterion
from analysis.water_bodies import WaterBodiesCriterion
from analysis.population_density import PopulationDensityCriterion

router = APIRouter(prefix="/gis", tags=["gis"])

ROADS_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlinesComprehensive/MapServer/0"
)

TRANSMISSION_LINES_LAYER_URL = (
    "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/"
    "HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0"
)

SUBSTATIONS_LAYER_URL = (
    "https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/"
    "Electric_Substations/FeatureServer/0"
)

FEMA_FLOODPLAIN_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Hydrology/MD_Floodplain/FeatureServer/1"
)

PROTECTED_LANDS_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Environment/MD_ProtectedLands/FeatureServer"
)

WATERBODIES_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Hydrology/MD_Waterbodies/FeatureServer"
)

flood_hazard_criterion = FloodHazardCriterion(
    layer_url=FEMA_FLOODPLAIN_URL,
    buffer_m=91.0,
)

protected_areas_criterion = ProtectedAreasCriterion(
    service_url=PROTECTED_LANDS_URL
)

water_bodies_criterion = WaterBodiesCriterion(
    service_url=WATERBODIES_URL,
    search_radius_m=5000.0,
)

population_density_criterion = PopulationDensityCriterion()

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
    criterion = DistanceCriterion(
        criterion_name="road_access",
        source_layer="Maryland Road Centerlines - Comprehensive",
        layer_url=ROADS_LAYER_URL,
        preferred_distance_key="road_m",
        search_delta_degrees=0.10,
        result_record_count=500,
    )

    result = criterion.evaluate(lat=lat, lon=lon)
    result["study_area"] = "Prince George's County"
    return result


@router.get("/power/transmission/access-score")
def get_transmission_access_score(lat: float, lon: float):
    criterion = DistanceCriterion(
        criterion_name="grid_infrastructure",
        source_layer="HIFLD Electric Power Transmission Lines",
        layer_url=TRANSMISSION_LINES_LAYER_URL,
        preferred_distance_key="transmission_line_m",
        search_delta_degrees=0.25,
        result_record_count=500,
    )

    return criterion.evaluate(lat=lat, lon=lon)


@router.get("/power/substations/access-score")
def get_substation_access_score(lat: float, lon: float):
    criterion = DistanceCriterion(
        criterion_name="grid_infrastructure",
        source_layer="Electric Substations",
        layer_url=SUBSTATIONS_LAYER_URL,
        preferred_distance_key="substation_m",
        search_delta_degrees=0.25,
        result_record_count=500,
    )

    return criterion.evaluate(lat=lat, lon=lon)

@router.get("/flood/fema/hazard-score")
def fema_flood_hazard_score(
    lat: float,
    lon: float,
) -> dict:
    return flood_hazard_criterion.evaluate(
        lat=lat,
        lon=lon,
    )

@router.get("/protected-areas/hazard-score")
def protected_areas_score(
    lat: float,
    lon: float,
) -> dict:
    return protected_areas_criterion.evaluate(
        lat=lat,
        lon=lon,
    )

@router.get("/water-bodies/proximity")
def water_bodies_proximity(
    lat: float,
    lon: float,
) -> dict:
    return water_bodies_criterion.evaluate(
        lat=lat,
        lon=lon,
    )

@router.get("/population-density/local-tract-score")
def population_density_score(
    lat: float,
    lon: float,
) -> dict:
    return population_density_criterion.evaluate(
        lat=lat,
        lon=lon,
    )

telecom_infrastructure_criterion = TelecomInfrastructureCriterion()


@router.get("/telecom/fiber-availability-score")
def telecom_fiber_availability_score(
    lat: float,
    lon: float,
) -> dict:
    return telecom_infrastructure_criterion.evaluate(
        lat=lat,
        lon=lon,
    )

