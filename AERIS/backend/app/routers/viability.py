from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from analysis.viability.service import ViabilityService
from app.config import get_build_token
from app.routers import parcels, statewide
from app.schemas.parcels import BuildJob
from app.schemas.viability import (
    SearchAreaBuildRequest,
    ViabilityCompareRequest,
    ViabilityCompareResponse,
    ViabilityMethodologyResponse,
    ViabilityScopeResponse,
)


PROJECT_DIRECTORY = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_DIRECTORY / "configs" / "viability" / "data_center_maryland.yaml"

router = APIRouter(prefix="/analysis/viability", tags=["viability"])

service = ViabilityService(
    config_path=CONFIG_PATH,
    statewide_service=statewide.service,
    site_service=parcels.site_feasibility_service,
    grid_service=parcels.grid_feasibility_service,
    planning_service=parcels.planning_service,
)


def require_build_authorization(supplied_token: str | None) -> None:
    configured_token = get_build_token()
    if configured_token is None:
        return
    if supplied_token != configured_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Build authorization failed.",
        )


@router.get("/methodology", response_model=ViabilityMethodologyResponse)
def viability_methodology() -> dict:
    return {"methodology": service.methodology()}


@router.get("/search-areas")
def viability_search_areas(
    mode: Literal["auto", "exploration"] = "auto",
    minimum_score: float | None = Query(default=None, ge=0.0, le=1.0),
    maximum_score: float | None = Query(default=None, ge=0.0, le=1.0),
    county: str | None = None,
) -> JSONResponse:
    if (
        minimum_score is not None
        and maximum_score is not None
        and minimum_score > maximum_score
    ):
        raise HTTPException(
            status_code=422,
            detail="minimum_score cannot exceed maximum_score",
        )
    try:
        payload = service.search_areas(
            mode=mode,
            minimum_score=minimum_score,
            maximum_score=maximum_score,
            county=county,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.post(
    "/search-areas/{zone_id}/evaluate",
    response_model=BuildJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def evaluate_search_area(
    zone_id: str,
    options: SearchAreaBuildRequest,
    build_token: str | None = Header(default=None, alias="X-AERIS-Build-Token"),
) -> dict:
    require_build_authorization(build_token)
    try:
        return parcels.build_coordinator.submit_zone(
            zone_id=zone_id,
            refresh=options.refresh,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=f"Search area {zone_id!r} was not found.",
        ) from error


@router.get(
    "/scopes/{scope_id}",
    response_model=ViabilityScopeResponse,
)
def viability_scope(
    scope_id: str,
    response: Response,
    include_all: bool = False,
) -> dict:
    result = service.evaluate_scope(scope_id=scope_id, include_all=include_all)
    response.headers["Cache-Control"] = "public, max-age=120"
    return result


@router.post(
    "/scopes/{scope_id}/compare",
    response_model=ViabilityCompareResponse,
)
def compare_viability_candidates(
    scope_id: str,
    request: ViabilityCompareRequest,
) -> dict:
    try:
        candidates = service.compare_candidates(
            scope_id=scope_id,
            candidate_ids=request.candidate_ids,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"scope_id": scope_id, "candidates": candidates}
