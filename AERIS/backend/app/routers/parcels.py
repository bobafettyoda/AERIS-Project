from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status

from analysis.parcels.api_service import ParcelDataService
from analysis.parcels.build_jobs import ScopeBuildCoordinator
from analysis.parcels.envelope_api_service import ParcelEnvelopeService
from analysis.parcels.grid_feasibility_api_service import (
    ParcelGridFeasibilityService,
)
from analysis.parcels.pipeline import scope_from_bbox, scope_from_zone
from analysis.planning.planning_api_service import PlanningContextService
from analysis.site_feasibility.api_service import SiteFeasibilityService
from app.config import get_build_token
from app.schemas.parcels import (
    BuildBBoxRequest,
    BuildJob,
    BuildZoneRequest,
    GeoJSONFeatureCollection,
    ParcelDetailResponse,
    PlanningRegistrySummary,
    ScopeBundle,
    SiteCandidateComparisonRequest,
    SiteCandidateComparisonResponse,
    SiteCandidateListResponse,
)


PROJECT_DIRECTORY = Path(__file__).resolve().parents[3]

CONFIG_PATH = PROJECT_DIRECTORY / "configs" / "parcels" / "maryland_parcels.yaml"
ENVELOPE_CONFIG_PATH = (
    PROJECT_DIRECTORY / "configs" / "parcels" / "development_envelopes.yaml"
)
GRID_FEASIBILITY_CONFIG_PATH = (
    PROJECT_DIRECTORY / "configs" / "parcels" / "grid_feasibility.yaml"
)
PLANNING_CONFIG_PATH = (
    PROJECT_DIRECTORY / "configs" / "planning" / "statewide_planning.yaml"
)
SITE_FEASIBILITY_CONFIG_PATH = (
    PROJECT_DIRECTORY / "configs" / "parcels" / "site_feasibility.yaml"
)

router = APIRouter(prefix="/analysis/parcels", tags=["parcels"])

service = ParcelDataService(CONFIG_PATH)
envelope_service = ParcelEnvelopeService(ENVELOPE_CONFIG_PATH)
grid_feasibility_service = ParcelGridFeasibilityService(
    GRID_FEASIBILITY_CONFIG_PATH
)
planning_service = PlanningContextService(PLANNING_CONFIG_PATH)
site_feasibility_service = SiteFeasibilityService(SITE_FEASIBILITY_CONFIG_PATH)
build_coordinator = ScopeBuildCoordinator(
    parcel_service=service,
    envelope_service=envelope_service,
    grid_service=grid_feasibility_service,
    planning_service=planning_service,
    site_service=site_feasibility_service,
    runtime_directory=PROJECT_DIRECTORY / "data" / "runtime" / "parcel_builds",
)


def cache_response(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=300"



def require_build_authorization(
    supplied_token: str | None,
) -> None:
    configured_token = get_build_token()
    if configured_token is None:
        return
    if supplied_token != configured_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Build authorization failed.",
        )


def build_required(scope_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "status": "scope_build_required",
            "scope_id": scope_id,
            "message": (
                "Build the scope with POST /analysis/parcels/build/zone/{zone_id} "
                "or POST /analysis/parcels/build/bbox before reading artifacts."
            ),
        },
    )


@router.get("/health")
def parcel_health() -> dict[str, Any]:
    result = service.health()
    if not result["ready"]:
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/scopes")
def parcel_scopes() -> dict[str, Any]:
    return {"scopes": service.list_scopes()}


@router.post(
    "/build/zone/{zone_id}",
    response_model=BuildJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_zone_scope(
    zone_id: str,
    options: BuildZoneRequest,
    build_token: str | None = Header(default=None, alias="X-AERIS-Build-Token"),
) -> dict[str, Any]:
    require_build_authorization(build_token)
    try:
        return build_coordinator.submit_zone(
            zone_id=zone_id,
            refresh=options.refresh,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate zone {zone_id!r} was not found.",
        ) from error


@router.post(
    "/build/bbox",
    response_model=BuildJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_bbox_scope(
    options: BuildBBoxRequest,
    build_token: str | None = Header(default=None, alias="X-AERIS-Build-Token"),
) -> dict[str, Any]:
    require_build_authorization(build_token)
    try:
        return build_coordinator.submit_bbox(
            west=options.west,
            south=options.south,
            east=options.east,
            north=options.north,
            scope_name=options.scope_name,
            refresh=options.refresh,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/jobs/{job_id}", response_model=BuildJob)
def parcel_build_job(job_id: str) -> dict[str, Any]:
    try:
        return build_coordinator.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Build job was not found.") from error


@router.get("/scopes/{scope_id}/status")
def parcel_scope_status(scope_id: str) -> dict[str, Any]:
    return {
        "scope_id": scope_id,
        "artifacts": build_coordinator.artifact_status(scope_id),
    }


@router.get("/scopes/{scope_id}/bundle", response_model=ScopeBundle)
def parcel_scope_bundle(
    scope_id: str,
    response: Response,
    limit: int = Query(default=8000, ge=1, le=8000),
) -> dict[str, Any]:
    try:
        payload = build_coordinator.bundle(scope_id=scope_id, limit=limit)
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return payload


@router.get("/zone/{zone_id}", response_model=GeoJSONFeatureCollection)
def parcels_for_zone(
    zone_id: str,
    response: Response,
    limit: int = Query(default=8000, ge=1, le=8000),
) -> dict[str, Any]:
    try:
        scope = scope_from_zone(
            config=service.config,
            project_directory=service.project_directory,
            zone_id=zone_id,
        )
        payload = service.feature_collection(scope_id=scope.scope_id, limit=limit)
    except KeyError as error:
        scope_id = f"zone-{zone_id.strip().lower()}"
        raise build_required(scope_id) from error
    cache_response(response)
    return payload


@router.get("/bbox", response_model=GeoJSONFeatureCollection)
def parcels_for_bbox(
    response: Response,
    west: float,
    south: float,
    east: float,
    north: float,
    scope_name: str | None = None,
    limit: int = Query(default=8000, ge=1, le=8000),
) -> dict[str, Any]:
    try:
        scope = scope_from_bbox(
            west=west,
            south=south,
            east=east,
            north=north,
            scope_name=scope_name,
        )
        payload = service.feature_collection(scope_id=scope.scope_id, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except KeyError as error:
        raise build_required(scope.scope_id) from error
    cache_response(response)
    return payload


@router.get(
    "/scopes/{scope_id}/parcels/{parcel_id}",
    response_model=ParcelDetailResponse,
)
def parcel_detail(scope_id: str, parcel_id: str) -> dict[str, Any]:
    try:
        result = service.parcel_detail(scope_id=scope_id, parcel_id=parcel_id)
        try:
            result["development_envelope"] = envelope_service.parcel_metrics(
                scope_id=scope_id,
                parcel_id=parcel_id,
            )
        except KeyError:
            result["development_envelope"] = None

        try:
            result["grid_feasibility"] = grid_feasibility_service.parcel_metrics(
                scope_id=scope_id,
                parcel_id=parcel_id,
            )
        except KeyError:
            result["grid_feasibility"] = None

        try:
            result["planning_context"] = planning_service.parcel_metrics(
                scope_id=scope_id,
                parcel_id=parcel_id,
            )
        except KeyError:
            result["planning_context"] = None

        try:
            result["site_feasibility"] = site_feasibility_service.parcel_metrics(
                scope_id=scope_id,
                parcel_id=parcel_id,
            )
        except KeyError:
            result["site_feasibility"] = None
        return result
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail="Parcel or parcel scope was not found.",
        ) from error


def read_envelope_layer(
    *,
    scope_id: str,
    layer: str,
    response: Response,
) -> dict[str, Any]:
    try:
        payload = envelope_service.feature_collection(scope_id=scope_id, layer=layer)
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return payload


@router.get(
    "/scopes/{scope_id}/development-envelopes",
    response_model=GeoJSONFeatureCollection,
)
def development_envelopes(scope_id: str, response: Response) -> dict[str, Any]:
    return read_envelope_layer(
        scope_id=scope_id,
        layer="development_envelopes",
        response=response,
    )


@router.get(
    "/scopes/{scope_id}/largest-components",
    response_model=GeoJSONFeatureCollection,
)
def largest_components(scope_id: str, response: Response) -> dict[str, Any]:
    return read_envelope_layer(
        scope_id=scope_id,
        layer="largest_components",
        response=response,
    )


@router.get(
    "/scopes/{scope_id}/constraints",
    response_model=GeoJSONFeatureCollection,
)
def parcel_constraints(scope_id: str, response: Response) -> dict[str, Any]:
    return read_envelope_layer(
        scope_id=scope_id,
        layer="scope_constraints",
        response=response,
    )


@router.get(
    "/scopes/{scope_id}/grid-evidence",
    response_model=GeoJSONFeatureCollection,
)
def parcel_grid_evidence(scope_id: str, response: Response) -> dict[str, Any]:
    try:
        payload = grid_feasibility_service.grid_evidence(scope_id=scope_id)
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return payload


@router.get("/planning/registry", response_model=PlanningRegistrySummary)
def planning_registry() -> dict[str, Any]:
    return planning_service.registry_summary()


@router.get(
    "/scopes/{scope_id}/planning-evidence",
    response_model=GeoJSONFeatureCollection,
)
def planning_evidence(scope_id: str, response: Response) -> dict[str, Any]:
    try:
        payload = planning_service.overlays(scope_id=scope_id)
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return payload

@router.get(
    "/scopes/{scope_id}/site-evidence",
    response_model=GeoJSONFeatureCollection,
)
def parcel_site_evidence(scope_id: str, response: Response) -> dict[str, Any]:
    try:
        payload = site_feasibility_service.site_evidence(scope_id=scope_id)
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return payload


@router.get(
    "/scopes/{scope_id}/site-candidates",
    response_model=SiteCandidateListResponse,
)
def parcel_site_candidates(
    scope_id: str,
    response: Response,
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    try:
        candidates = site_feasibility_service.top_candidates(
            scope_id=scope_id,
            limit=limit,
        )
    except KeyError as error:
        raise build_required(scope_id) from error
    cache_response(response)
    return {"scope_id": scope_id, "candidates": candidates}


@router.post(
    "/scopes/{scope_id}/compare-site-candidates",
    response_model=SiteCandidateComparisonResponse,
)
def compare_site_candidates(
    scope_id: str,
    request: SiteCandidateComparisonRequest,
) -> dict[str, Any]:
    try:
        candidates = site_feasibility_service.compare_candidates(
            scope_id=scope_id,
            candidate_ids=request.candidate_ids,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=f"One or more site candidates were not found: {error}",
        ) from error
    return {"scope_id": scope_id, "candidates": candidates}
