from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.parcels import ApiModel, GeoJSONFeatureCollection


class StatewideGridSummary(ApiModel):
    cell_count: int
    complete_cells: int
    insufficient_data_cells: int
    hard_excluded_cells: int
    auto_screen_eligible_cells: int
    exploration_screen_eligible_cells: int


class StatewideAuditSummary(ApiModel):
    status: str | None = None
    release_status: str | None = None
    screening_shortlist_ready: bool | None = None
    automated_recommendation_ready: bool = False
    material_flags: dict[str, Any] = Field(default_factory=dict)


class StatewideScoreBand(ApiModel):
    id: str
    label: str
    minimum: float
    maximum: float
    auto_cell_count: int | None = None
    exploration_cell_count: int | None = None


class StatewideBounds(ApiModel):
    west: float
    south: float
    east: float
    north: float


class StatewideCounty(ApiModel):
    fips: str
    name: str


class StatewideSummaryResponse(ApiModel):
    project: str
    analysis: str
    model_version: str | None = None
    grid: StatewideGridSummary
    zones: dict[str, int] = Field(default_factory=dict)
    audit: StatewideAuditSummary
    score_statistics: dict[str, float | None] = Field(default_factory=dict)
    effective_score_statistics: dict[str, float | None] = Field(default_factory=dict)
    score_bands: list[StatewideScoreBand] = Field(default_factory=list)
    bounds: StatewideBounds
    counties: list[StatewideCounty] = Field(default_factory=list)
    terminology: dict[str, Any] = Field(default_factory=dict)
    required_next_stage: list[str] = Field(default_factory=list)


class StatewideLocation(ApiModel):
    latitude: float | None = None
    longitude: float | None = None
    county_fips: str | None = None
    county_name: str | None = None
    tract_geoid: str | None = None
    land_fraction: float | None = None
    cell_area_sq_km: float | None = None


class StatewideDecision(ApiModel):
    model_status: str | None = None
    hard_excluded: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    auto_screen_eligible: bool
    exploration_screen_eligible: bool
    automated_recommendation_ready: bool


class StatewideScores(ApiModel):
    technical_suitability: float | None = None
    effective_suitability: float | None = None
    criteria: dict[str, float | None] = Field(default_factory=dict)


class StatewideCellDetailResponse(ApiModel):
    cell_id: str
    location: StatewideLocation
    decision: StatewideDecision
    scores: StatewideScores
    evidence: dict[str, dict[str, Any]] = Field(default_factory=dict)
    community_impact: dict[str, Any] = Field(default_factory=dict)


class ZoneMembership(ApiModel):
    member_count: int
    member_cell_ids: list[str] = Field(default_factory=list)
    member_cell_ids_truncated: bool


class ZoneMemberSummary(ApiModel):
    technical_score: dict[str, float | None] = Field(default_factory=dict)
    equity_gate_counts: dict[str, int] = Field(default_factory=dict)
    county_counts: dict[str, int] = Field(default_factory=dict)


class StatewideZoneDetailResponse(ApiModel):
    zone_id: str
    mode: str
    properties: dict[str, Any] = Field(default_factory=dict)
    membership: ZoneMembership
    member_summary: ZoneMemberSummary
    interpretation: str


class StatewideHealthResponse(ApiModel):
    ready: bool
    root: str
    files: dict[str, dict[str, Any]]


__all__ = [
    "GeoJSONFeatureCollection",
    "StatewideCellDetailResponse",
    "StatewideHealthResponse",
    "StatewideSummaryResponse",
    "StatewideZoneDetailResponse",
]
