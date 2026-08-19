from __future__ import annotations

from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from fastapi.responses import JSONResponse

from analysis.parcels.api_service import (
    ParcelDataService,
)


PROJECT_DIRECTORY = (
    Path(__file__).resolve().parents[3]
)

CONFIG_PATH = (
    PROJECT_DIRECTORY
    / "configs"
    / "parcels"
    / "maryland_parcels.yaml"
)


router = APIRouter(
    prefix="/analysis/parcels",
    tags=["parcels"],
)

service = ParcelDataService(
    CONFIG_PATH
)


@router.get("/health")
def parcel_health() -> dict:
    result = service.health()

    if not result["ready"]:
        raise HTTPException(
            status_code=503,
            detail=result,
        )

    return result


@router.get("/scopes")
def parcel_scopes() -> dict:
    return {
        "scopes": (
            service.list_scopes()
        )
    }


@router.get("/zone/{zone_id}")
def parcels_for_zone(
    zone_id: str,
    refresh: bool = False,
    limit: int = Query(
        default=8000,
        ge=1,
        le=8000,
    ),
) -> JSONResponse:
    try:
        manifest = (
            service.build_zone(
                zone_id=zone_id,
                refresh=refresh,
            )
        )

        scope_id = manifest[
            "scope"
        ]["scope_id"]

        payload = (
            service.feature_collection(
                scope_id=scope_id,
                limit=limit,
            )
        )

        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": (
                    "public, max-age=300"
                ),
            },
        )

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Candidate zone "
                f"{zone_id!r} was not found."
            ),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


@router.get("/bbox")
def parcels_for_bbox(
    west: float,
    south: float,
    east: float,
    north: float,
    scope_name: str | None = None,
    refresh: bool = False,
    limit: int = Query(
        default=8000,
        ge=1,
        le=8000,
    ),
) -> JSONResponse:
    try:
        manifest = (
            service.build_bbox(
                west=west,
                south=south,
                east=east,
                north=north,
                scope_name=scope_name,
                refresh=refresh,
            )
        )

        scope_id = manifest[
            "scope"
        ]["scope_id"]

        payload = (
            service.feature_collection(
                scope_id=scope_id,
                limit=limit,
            )
        )

        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": (
                    "public, max-age=300"
                ),
            },
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


@router.get(
    "/scopes/{scope_id}/"
    "parcels/{parcel_id}"
)
def parcel_detail(
    scope_id: str,
    parcel_id: str,
) -> dict:
    try:
        return service.parcel_detail(
            scope_id=scope_id,
            parcel_id=parcel_id,
        )

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=(
                "Parcel or parcel scope "
                "was not found."
            ),
        ) from error
