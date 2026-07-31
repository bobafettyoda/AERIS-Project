from __future__ import annotations

import os


ROADS_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlinesComprehensive/MapServer/0"
)

TRANSMISSION_LINES_LAYER_URL = (
    "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/"
    "arcgis/rest/services/"
    "HIFLD_US_Electric_Power_Transmission_Lines/"
    "FeatureServer/0"
)

SUBSTATIONS_LAYER_URL = (
    "https://services5.arcgis.com/HDRa0B57OVrv2E1q/"
    "ArcGIS/rest/services/"
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

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def get_cors_origins() -> list[str]:
    configured = os.getenv(
        "AERIS_CORS_ORIGINS",
        "",
    ).strip()

    if not configured:
        return list(DEFAULT_CORS_ORIGINS)

    return [
        origin.strip()
        for origin in configured.split(",")
        if origin.strip()
    ]

MARYLAND_BOUNDARY_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Boundaries/MD_PoliticalBoundaries/FeatureServer/0"
)

MD_ENVIROSCREEN_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Environment/MD_EnviroScreen/FeatureServer/0"
)



MARYLAND_LAND_BOUNDARIES_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Boundaries/MD_PhysicalBoundaries/FeatureServer/1"
)

ROAD_INTERSTATES_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlines/MapServer/0"
)

ROAD_US_ROUTES_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlines/MapServer/1"
)

ROAD_MARYLAND_ROUTES_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "Transportation/MD_RoadCenterlines/MapServer/2"
)

FIBER_COVERAGE_LAYER_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "UtilityTelecom/MD_BroadbandServiceAreas/MapServer/3"
)

