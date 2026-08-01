from __future__ import annotations

from typing import Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from fastapi.responses import JSONResponse

from analysis.statewide.api_service import (
    StatewideDataService,
    StatewidePaths,
)


router = APIRouter(
    prefix="/analysis/statewide",
    tags=["statewide"],
)

service = StatewideDataService(
    StatewidePaths.from_environment()
)


def unavailable(
    error: Exception,
) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "status": (
                "statewide_data_unavailable"
            ),
            "message": str(error),
        },
    )


@router.get("/health")
def statewide_health() -> dict:
    result = service.health()

    if not result["ready"]:
        raise HTTPException(
            status_code=503,
            detail=result,
        )

    return result


@router.get("/summary")
def statewide_summary() -> dict:
    try:
        return service.summary()

    except FileNotFoundError as error:
        raise unavailable(error) from error


@router.get("/grid")
def statewide_grid(
    score_type: Literal[
        "technical",
        "effective",
    ] = "technical",
    minimum_score: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
    ),
    maximum_score: float = Query(
        default=1.0,
        ge=0.0,
        le=1.0,
    ),
    eligibility: Literal[
        "all",
        "auto",
        "exploration",
    ] = "all",
    equity_gate: str | None = None,
    excluded: bool | None = None,
    county: str | None = None,
    limit: int = Query(
        default=30000,
        ge=1,
        le=30000,
    ),
) -> JSONResponse:
    if minimum_score > maximum_score:
        raise HTTPException(
            status_code=422,
            detail=(
                "minimum_score cannot exceed "
                "maximum_score"
            ),
        )

    equity_gates = (
        [
            value.strip()
            for value
            in equity_gate.split(",")
            if value.strip()
        ]
        if equity_gate
        else None
    )

    try:
        payload = (
            service.grid_feature_collection(
                score_type=score_type,
                minimum_score=(
                    minimum_score
                ),
                maximum_score=(
                    maximum_score
                ),
                eligibility=eligibility,
                equity_gates=(
                    equity_gates
                ),
                excluded=excluded,
                county=county,
                limit=limit,
            )
        )

    except FileNotFoundError as error:
        raise unavailable(error) from error

    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": (
                "public, max-age=300"
            ),
        },
    )


@router.get("/candidate-zones")
def statewide_candidate_zones(
    mode: Literal[
        "top",
        "auto",
        "exploration",
    ] = "top",
    minimum_score: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
    ),
    maximum_score: float = Query(
        default=1.0,
        ge=0.0,
        le=1.0,
    ),
    county: str | None = None,
    top_n: int | None = Query(
        default=None,
        ge=1,
        le=100,
    ),
) -> JSONResponse:
    try:
        payload = (
            service.zone_feature_collection(
                mode=mode,
                minimum_score=(
                    minimum_score
                ),
                maximum_score=(
                    maximum_score
                ),
                county=county,
                top_n=top_n,
            )
        )

    except FileNotFoundError as error:
        raise unavailable(error) from error

    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": (
                "public, max-age=300"
            ),
        },
    )


@router.get("/cells/{cell_id}")
def statewide_cell_detail(
    cell_id: str,
) -> dict:
    try:
        return service.cell_detail(
            cell_id
        )

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Statewide grid cell "
                f"{cell_id!r} was not found."
            ),
        ) from error

    except FileNotFoundError as error:
        raise unavailable(error) from error


@router.get("/zones/{zone_id}")
def statewide_zone_detail(
    zone_id: str,
) -> dict:
    try:
        return service.zone_detail(
            zone_id
        )

    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Candidate zone "
                f"{zone_id!r} was not found."
            ),
        ) from error

    except FileNotFoundError as error:
        raise unavailable(error) from error


@router.get("/score-bands")
def statewide_score_bands() -> dict:
    try:
        return (
            service.score_band_summary()
        )

    except FileNotFoundError as error:
        raise unavailable(error) from error


@router.get("/bias-audit")
def statewide_bias_audit() -> dict:
    try:
        return service.bias_audit()

    except FileNotFoundError as error:
        raise unavailable(error) from error
