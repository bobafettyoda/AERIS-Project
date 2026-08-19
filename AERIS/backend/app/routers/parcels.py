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
from analysis.parcels.envelope_api_service import (
    ParcelEnvelopeService,
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

ENVELOPE_CONFIG_PATH = (
    PROJECT_DIRECTORY
    / "configs"
    / "parcels"
    / "development_envelopes.yaml"
)

envelope_service = (
    ParcelEnvelopeService(
        ENVELOPE_CONFIG_PATH
    )
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
        result = service.parcel_detail(
            scope_id=scope_id,
            parcel_id=parcel_id,
        )

        try:
            result[
                "development_envelope"
            ] = (
                envelope_service
                .parcel_metrics(
                    scope_id=scope_id,
                    parcel_id=parcel_id,
                )
            )

        except KeyError:
            result[
                "development_envelope"
            ] = None

        return result

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=(
                "Parcel or parcel scope "
                "was not found."
            ),
        ) from error

@router.get(
    "/scopes/{scope_id}/"
    "development-envelopes"
)
def development_envelopes(
    scope_id: str,
    refresh: bool = False,
) -> JSONResponse:
    try:
        envelope_service.build(
            scope_id=scope_id,
            refresh=refresh,
        )

        payload = (
            envelope_service
            .feature_collection(
                scope_id=scope_id,
                layer=(
                    "development_envelopes"
                ),
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
                "Parcel scope was not found."
            ),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


@router.get(
    "/scopes/{scope_id}/"
    "largest-components"
)
def largest_components(
    scope_id: str,
) -> JSONResponse:
    try:
        envelope_service.build(
            scope_id=scope_id,
        )

        payload = (
            envelope_service
            .feature_collection(
                scope_id=scope_id,
                layer=(
                    "largest_components"
                ),
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

    except (
        KeyError,
        RuntimeError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


@router.get(
    "/scopes/{scope_id}/"
    "constraints"
)
def parcel_constraints(
    scope_id: str,
) -> JSONResponse:
    try:
        envelope_service.build(
            scope_id=scope_id,
        )

        payload = (
            envelope_service
            .feature_collection(
                scope_id=scope_id,
                layer=(
                    "scope_constraints"
                ),
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

    except (
        KeyError,
        RuntimeError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

