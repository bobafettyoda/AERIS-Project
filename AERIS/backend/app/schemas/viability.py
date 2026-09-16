from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.parcels import ApiModel, BuildJob, GeoJSONFeatureCollection


class ViabilityCounts(ApiModel):
    evaluated: int = 0
    comparison_eligible: int = 0
    evidence_hold: int = 0
    rejected: int = 0


class ViabilityCandidate(ApiModel):
    candidate_id: str
    candidate_kind: str
    parcel_id: str | None = None
    parcel_count: int | None = None
    parcel_ids: str | None = None
    assemblage_status: str | None = None
    candidate_score: float | None = None
    viability_score: float | None = None
    viability_status: str
    comparison_eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    hold_reasons: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    site_feasibility_class: str | None = None
    final_site_area_acres: float | None = None
    total_site_area_acres: float | None = None
    largest_contiguous_site_acres: float | None = None
    road_access_status: str | None = None
    mapped_wetland_fraction: float | None = None
    steep_slope_fraction: float | None = None
    building_reference_fraction: float | None = None
    redevelopment_burden_class: str | None = None
    regional_technical_score: float | None = None
    regional_effective_score: float | None = None
    grid_context_class: str | None = None
    grid_data_confidence: str | None = None
    capacity_status: str | None = None
    planning_review_status: str | None = None
    planning_data_confidence: str | None = None
    availability_confirmed: bool | None = None


class ViabilityScopeResponse(ApiModel):
    scope_id: str
    scope_status: str
    artifact_readiness: dict[str, bool] = Field(default_factory=dict)
    missing_artifacts: list[str] = Field(default_factory=list)
    counts: ViabilityCounts
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    hold_reason_counts: dict[str, int] = Field(default_factory=dict)
    review_reason_counts: dict[str, int] = Field(default_factory=dict)
    comparison_candidates: list[ViabilityCandidate] = Field(default_factory=list)
    evaluated_candidates: list[ViabilityCandidate] = Field(default_factory=list)
    safeguards: dict[str, bool] = Field(default_factory=dict)
    interpretation: dict[str, Any] = Field(default_factory=dict)


class ViabilityCompareRequest(ApiModel):
    candidate_ids: list[str] = Field(min_length=2, max_length=5)


class ViabilityCompareResponse(ApiModel):
    scope_id: str
    candidates: list[ViabilityCandidate]


class SearchAreaBuildRequest(ApiModel):
    refresh: bool = False


class ViabilityMethodologyResponse(ApiModel):
    methodology: dict[str, Any]


__all__ = [
    "BuildJob",
    "GeoJSONFeatureCollection",
    "SearchAreaBuildRequest",
    "ViabilityCandidate",
    "ViabilityCompareRequest",
    "ViabilityCompareResponse",
    "ViabilityMethodologyResponse",
    "ViabilityScopeResponse",
]
