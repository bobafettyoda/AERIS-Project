from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


AvailabilityStatus = Literal[
    "PUBLIC_OR_INSTITUTIONAL",
    "EXISTING_USE_REVIEW_REQUIRED",
    "DATA_INSUFFICIENT",
    "POTENTIAL_FURTHER_REVIEW",
]

DataConfidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]

GridContextClass = Literal[
    "VERY_STRONG_MAPPED_GRID_CONTEXT",
    "STRONG_MAPPED_GRID_CONTEXT",
    "MODERATE_MAPPED_GRID_CONTEXT",
    "LIMITED_MAPPED_GRID_CONTEXT",
    "INSUFFICIENT_MAPPED_GRID_DATA",
]

CapacityStatus = Literal["UNKNOWN_NOT_IN_PUBLIC_SOURCE"]

PlanningSourceStatus = Literal[
    "AVAILABLE",
    "STATEWIDE_BASELINE_ONLY",
    "PARTIAL",
    "SOURCE_DISCOVERY_REQUIRED",
    "MANUAL_REVIEW_REQUIRED",
    "DATA_UNAVAILABLE",
    "ERROR",
]


class ArtifactStatus(ApiModel):
    state: Literal["pending", "running", "ready", "missing", "failed"]
    error: str | None = None
    updated_at_utc: str | None = None


class BuildZoneRequest(ApiModel):
    refresh: bool = False


class BuildBBoxRequest(ApiModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    scope_name: str | None = None
    refresh: bool = False


class BuildJob(ApiModel):
    job_id: str
    scope_id: str
    state: Literal[
        "queued",
        "running",
        "completed",
        "partial_failure",
        "failed",
    ]
    target: dict[str, Any]
    refresh: bool
    created_at_utc: str
    updated_at_utc: str
    current_stage: str
    progress: float = Field(ge=0, le=1)
    artifacts: dict[str, ArtifactStatus]
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class GeoJSONFeatureCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScopeBundle(ApiModel):
    scope_id: str
    artifacts: dict[str, ArtifactStatus]
    parcels: GeoJSONFeatureCollection
    envelopes: GeoJSONFeatureCollection | None = None
    constraints: GeoJSONFeatureCollection | None = None
    grid: GeoJSONFeatureCollection | None = None
    planning: GeoJSONFeatureCollection | None = None


class ParcelIdentity(ApiModel):
    account_id: str | None = None
    jurisdiction_code: str | None = None
    county_fips: str | None = None
    county_name: str | None = None
    property_address: str | None = None


class ParcelCore(ApiModel):
    parcel_area_acres: float | None = None
    source_reported_acres: float | None = None
    geometry_area_acres: float | None = None
    land_use_code: str | None = None
    land_use_description: str | None = None
    zoning_code: str | None = None
    commercial_industrial_use: str | None = None
    public_water_status: str | None = None
    public_sewer_status: str | None = None


class ParcelClassification(ApiModel):
    public_land_flag: bool
    institutional_use_flag: bool
    existing_development_indicator: bool
    availability_status: AvailabilityStatus | None = None
    availability_reason: str | None = None
    availability_confirmed: bool = False
    data_confidence: DataConfidence | None = None
    public_classification_evidence: str | None = None
    institutional_classification_evidence: str | None = None


class ParcelStatewideContext(ApiModel):
    cell_id: str | None = None
    technical_score: float | None = None
    effective_score: float | None = None
    equity_gate: str | None = None
    hard_excluded: bool | None = None
    auto_eligible: bool | None = None
    exploration_eligible: bool | None = None


class ParcelScopeContext(ApiModel):
    candidate_zone_id: str | None = None
    candidate_zone_mode: str | None = None
    overlap_fraction: float | None = None
    overlap_area_acres: float | None = None
    statewide_link_method: str | None = None
    statewide_context_distance_m: float | None = None


class DevelopmentEnvelopeEvidence(ApiModel):
    status: str | None = None
    analysis_area_acres: float | None = None
    water_overlap_acres: float | None = None
    protected_lands_overlap_acres: float | None = None
    sfha_overlap_acres: float | None = None
    aviation_overlap_acres: float | None = None
    aviation_notice_screening_overlap_acres: float | None = None
    aviation_notice_screening_status: str | None = None
    faa_determination_made: bool = False
    mapped_constrained_area_acres: float | None = None
    preliminary_unconstrained_area_acres: float | None = None
    preliminary_unconstrained_fraction: float | None = None
    largest_contiguous_unconstrained_acres: float | None = None
    largest_contiguous_fraction: float | None = None
    unconstrained_component_count: int | None = None
    mapped_constraint_types: str | None = None
    preliminary_envelope_only: bool = True


class NearestTransmissionEvidence(ApiModel):
    distance_m: float | None = None
    id: str | None = None
    type: str | None = None
    status: str | None = None
    owner: str | None = None
    voltage_kv: float | None = None
    voltage_class: str | None = None
    source_voltage_class: str | None = None
    inferred: bool | None = None
    substation_1: str | None = None
    substation_2: str | None = None
    source_date: str | None = None
    validation_method: str | None = None
    data_confidence: str | None = None


class TransmissionSummaryEvidence(ApiModel):
    feature_count: int | None = None
    known_voltage_count: int | None = None
    maximum_voltage_kv: float | None = None
    distinct_owner_count: int | None = None
    owners: str | None = None


class NearestSubstationEvidence(ApiModel):
    distance_m: float | None = None
    id: str | None = None
    name: str | None = None
    type: str | None = None
    status: str | None = None
    line_count: int | None = None
    maximum_voltage_kv: float | None = None
    minimum_voltage_kv: float | None = None
    voltage_class: str | None = None
    source_date: str | None = None
    validation_method: str | None = None
    data_confidence: str | None = None


class SubstationSummaryEvidence(ApiModel):
    feature_count: int | None = None
    known_voltage_count: int | None = None
    maximum_voltage_kv: float | None = None


class CapacityEvidence(ApiModel):
    status: CapacityStatus
    available_capacity_mw: None = None
    utility_confirmation_required: bool = True
    interconnection_study_required: bool = True
    electrical_service_feasibility_confirmed: bool = False


class GridFeasibilityEvidence(ApiModel):
    grid_feasibility_status: str | None = None
    public_grid_context_class: GridContextClass | None = None
    grid_data_confidence: DataConfidence | None = None
    statewide_grid_infrastructure_score: float | None = None
    nearest_transmission: NearestTransmissionEvidence
    transmission_within_5km: TransmissionSummaryEvidence
    nearest_substation: NearestSubstationEvidence
    substations_within_10km: SubstationSummaryEvidence
    capacity: CapacityEvidence
    warning: str


class PlanningJurisdictionEvidence(ApiModel):
    county_fips: str | None = None
    county_name: str | None = None
    municipality_name: str | None = None
    municipality_overlap_acres: float | None = None
    municipality_overlap_fraction: float | None = None
    municipality_assignment_method: str | None = None
    authority_profile: str | None = None
    authority_level: str | None = None
    authority_name: str | None = None
    authority_status: str | None = None


class PlanningZoningEvidence(ApiModel):
    statewide_code: str | None = None
    statewide_status: str | None = None
    local_source_status: PlanningSourceStatus | None = None
    local_source_note: str | None = None
    local_verified: bool = False
    permitted_use_determined: bool = False


class PlanningSourcesEvidence(ApiModel):
    comprehensive_plan: PlanningSourceStatus | None = None
    active_development: PlanningSourceStatus | None = None
    permits: PlanningSourceStatus | None = None


class PlanningAdapterEvidence(ApiModel):
    name: str | None = None
    available: bool = False
    zoning_status: str | None = None
    active_development_status: str | None = None
    permit_status: str | None = None
    warning: str | None = None


class PlanningOverlayEvidence(ApiModel):
    priority_funding_area: str | None = None
    priority_funding_area_overlap_acres: float | None = None
    priority_funding_area_overlap_fraction: float | None = None
    priority_funding_area_assignment_method: str | None = None
    critical_area_overlap: bool = False
    critical_area_overlap_acres: float | None = None
    enterprise_zone_count: int | None = None
    enterprise_zone_names: str | None = None
    sustainable_community_count: int | None = None
    sustainable_community_names: str | None = None
    foreign_trade_zone_count: int | None = None
    foreign_trade_zone_names: str | None = None
    rise_zone_count: int | None = None
    rise_zone_names: str | None = None
    opportunity_zone_count: int | None = None
    opportunity_zone_names: str | None = None


class PlanningDecisionEvidence(ApiModel):
    planning_review_status: str | None = None
    data_confidence: DataConfidence | None = None
    manual_local_verification_required: bool = True
    active_development_clear: bool = False
    permit_clearance_determined: bool = False
    entitlement_clearance_determined: bool = False


class PlanningContextEvidence(ApiModel):
    jurisdiction: PlanningJurisdictionEvidence
    zoning: PlanningZoningEvidence
    planning_sources: PlanningSourcesEvidence
    adapter: PlanningAdapterEvidence
    statewide_context: PlanningOverlayEvidence
    decision: PlanningDecisionEvidence
    warning: str


class ParcelDetailResponse(ApiModel):
    scope_id: str
    parcel_id: str
    identity: ParcelIdentity
    parcel: ParcelCore
    source_development_indicators: dict[str, Any]
    classification: ParcelClassification
    statewide_context: ParcelStatewideContext
    scope: ParcelScopeContext
    source_dates: dict[str, str | None]
    development_envelope: DevelopmentEnvelopeEvidence | None = None
    grid_feasibility: GridFeasibilityEvidence | None = None
    planning_context: PlanningContextEvidence | None = None
    warning: str


class PlanningRegistrySummary(ApiModel):
    jurisdiction_count: int
    county_fips: list[str]
    source_status_counts: dict[str, dict[str, int]]
