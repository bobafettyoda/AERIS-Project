// Generated from AERIS/backend/openapi.json. Do not edit manually.

export type ArtifactStatus = {
  state: "pending" | "running" | "ready" | "missing" | "failed";
  error?: string | null;
  updated_at_utc?: string | null;
  [key: string]: unknown;
};

export type BuildBBoxRequest = {
  west: number;
  south: number;
  east: number;
  north: number;
  scope_name?: string | null;
  refresh?: boolean;
  [key: string]: unknown;
};

export type BuildJob = {
  job_id: string;
  scope_id: string;
  state: "queued" | "running" | "completed" | "partial_failure" | "failed";
  target: {
  [key: string]: unknown;
};
  refresh: boolean;
  created_at_utc: string;
  updated_at_utc: string;
  current_stage: string;
  progress: number;
  artifacts: {
  [key: string]: ArtifactStatus;
};
  warnings?: Array<string>;
  error?: string | null;
  [key: string]: unknown;
};

export type BuildZoneRequest = {
  refresh?: boolean;
  [key: string]: unknown;
};

export type CapacityEvidence = {
  status: "UNKNOWN_NOT_IN_PUBLIC_SOURCE";
  available_capacity_mw?: null;
  utility_confirmation_required?: boolean;
  interconnection_study_required?: boolean;
  electrical_service_feasibility_confirmed?: boolean;
  [key: string]: unknown;
};

export type DevelopmentEnvelopeEvidence = {
  status?: string | null;
  analysis_area_acres?: number | null;
  water_overlap_acres?: number | null;
  protected_lands_overlap_acres?: number | null;
  sfha_overlap_acres?: number | null;
  aviation_overlap_acres?: number | null;
  aviation_notice_screening_overlap_acres?: number | null;
  aviation_notice_screening_status?: string | null;
  faa_determination_made?: boolean;
  mapped_constrained_area_acres?: number | null;
  preliminary_unconstrained_area_acres?: number | null;
  preliminary_unconstrained_fraction?: number | null;
  largest_contiguous_unconstrained_acres?: number | null;
  largest_contiguous_fraction?: number | null;
  unconstrained_component_count?: number | null;
  mapped_constraint_types?: string | null;
  preliminary_envelope_only?: boolean;
  [key: string]: unknown;
};

export type GeoJSONFeatureCollection = {
  type?: "FeatureCollection";
  features: Array<{
  [key: string]: unknown;
}>;
  metadata?: {
  [key: string]: unknown;
};
  [key: string]: unknown;
};

export type GridFeasibilityEvidence = {
  grid_feasibility_status?: string | null;
  public_grid_context_class?: "VERY_STRONG_MAPPED_GRID_CONTEXT" | "STRONG_MAPPED_GRID_CONTEXT" | "MODERATE_MAPPED_GRID_CONTEXT" | "LIMITED_MAPPED_GRID_CONTEXT" | "INSUFFICIENT_MAPPED_GRID_DATA" | null;
  grid_data_confidence?: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT" | null;
  statewide_grid_infrastructure_score?: number | null;
  nearest_transmission: NearestTransmissionEvidence;
  transmission_within_5km: TransmissionSummaryEvidence;
  nearest_substation: NearestSubstationEvidence;
  substations_within_10km: SubstationSummaryEvidence;
  capacity: CapacityEvidence;
  warning: string;
  [key: string]: unknown;
};

export type HTTPValidationError = {
  detail?: Array<ValidationError>;
};

export type NearestSubstationEvidence = {
  distance_m?: number | null;
  id?: string | null;
  name?: string | null;
  type?: string | null;
  status?: string | null;
  line_count?: number | null;
  maximum_voltage_kv?: number | null;
  minimum_voltage_kv?: number | null;
  voltage_class?: string | null;
  source_date?: string | null;
  validation_method?: string | null;
  data_confidence?: string | null;
  [key: string]: unknown;
};

export type NearestTransmissionEvidence = {
  distance_m?: number | null;
  id?: string | null;
  type?: string | null;
  status?: string | null;
  owner?: string | null;
  voltage_kv?: number | null;
  voltage_class?: string | null;
  source_voltage_class?: string | null;
  inferred?: boolean | null;
  substation_1?: string | null;
  substation_2?: string | null;
  source_date?: string | null;
  validation_method?: string | null;
  data_confidence?: string | null;
  [key: string]: unknown;
};

export type ParcelClassification = {
  public_land_flag: boolean;
  institutional_use_flag: boolean;
  existing_development_indicator: boolean;
  availability_status?: "PUBLIC_OR_INSTITUTIONAL" | "EXISTING_USE_REVIEW_REQUIRED" | "DATA_INSUFFICIENT" | "POTENTIAL_FURTHER_REVIEW" | null;
  availability_reason?: string | null;
  availability_confirmed?: boolean;
  data_confidence?: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT" | null;
  public_classification_evidence?: string | null;
  institutional_classification_evidence?: string | null;
  [key: string]: unknown;
};

export type ParcelCore = {
  parcel_area_acres?: number | null;
  source_reported_acres?: number | null;
  geometry_area_acres?: number | null;
  land_use_code?: string | null;
  land_use_description?: string | null;
  zoning_code?: string | null;
  commercial_industrial_use?: string | null;
  public_water_status?: string | null;
  public_sewer_status?: string | null;
  [key: string]: unknown;
};

export type ParcelDetailResponse = {
  scope_id: string;
  parcel_id: string;
  identity: ParcelIdentity;
  parcel: ParcelCore;
  source_development_indicators: {
  [key: string]: unknown;
};
  classification: ParcelClassification;
  statewide_context: ParcelStatewideContext;
  scope: ParcelScopeContext;
  source_dates: {
  [key: string]: string | null;
};
  development_envelope?: DevelopmentEnvelopeEvidence | null;
  grid_feasibility?: GridFeasibilityEvidence | null;
  planning_context?: PlanningContextEvidence | null;
  site_feasibility?: SiteFeasibilityEvidence | null;
  warning: string;
  [key: string]: unknown;
};

export type ParcelIdentity = {
  account_id?: string | null;
  jurisdiction_code?: string | null;
  county_fips?: string | null;
  county_name?: string | null;
  property_address?: string | null;
  [key: string]: unknown;
};

export type ParcelScopeContext = {
  candidate_zone_id?: string | null;
  candidate_zone_mode?: string | null;
  overlap_fraction?: number | null;
  overlap_area_acres?: number | null;
  statewide_link_method?: string | null;
  statewide_context_distance_m?: number | null;
  [key: string]: unknown;
};

export type ParcelStatewideContext = {
  cell_id?: string | null;
  technical_score?: number | null;
  effective_score?: number | null;
  equity_gate?: string | null;
  hard_excluded?: boolean | null;
  auto_eligible?: boolean | null;
  exploration_eligible?: boolean | null;
  [key: string]: unknown;
};

export type PlanningAdapterEvidence = {
  name?: string | null;
  available?: boolean;
  zoning_status?: string | null;
  active_development_status?: string | null;
  permit_status?: string | null;
  warning?: string | null;
  [key: string]: unknown;
};

export type PlanningContextEvidence = {
  jurisdiction: PlanningJurisdictionEvidence;
  zoning: PlanningZoningEvidence;
  planning_sources: PlanningSourcesEvidence;
  adapter: PlanningAdapterEvidence;
  statewide_context: PlanningOverlayEvidence;
  decision: PlanningDecisionEvidence;
  warning: string;
  [key: string]: unknown;
};

export type PlanningDecisionEvidence = {
  planning_review_status?: string | null;
  data_confidence?: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT" | null;
  manual_local_verification_required?: boolean;
  active_development_clear?: boolean;
  permit_clearance_determined?: boolean;
  entitlement_clearance_determined?: boolean;
  [key: string]: unknown;
};

export type PlanningJurisdictionEvidence = {
  county_fips?: string | null;
  county_name?: string | null;
  municipality_name?: string | null;
  municipality_overlap_acres?: number | null;
  municipality_overlap_fraction?: number | null;
  municipality_assignment_method?: string | null;
  authority_profile?: string | null;
  authority_level?: string | null;
  authority_name?: string | null;
  authority_status?: string | null;
  [key: string]: unknown;
};

export type PlanningOverlayEvidence = {
  priority_funding_area?: string | null;
  priority_funding_area_overlap_acres?: number | null;
  priority_funding_area_overlap_fraction?: number | null;
  priority_funding_area_assignment_method?: string | null;
  critical_area_overlap?: boolean;
  critical_area_overlap_acres?: number | null;
  enterprise_zone_count?: number | null;
  enterprise_zone_names?: string | null;
  sustainable_community_count?: number | null;
  sustainable_community_names?: string | null;
  foreign_trade_zone_count?: number | null;
  foreign_trade_zone_names?: string | null;
  rise_zone_count?: number | null;
  rise_zone_names?: string | null;
  opportunity_zone_count?: number | null;
  opportunity_zone_names?: string | null;
  [key: string]: unknown;
};

export type PlanningRegistrySummary = {
  jurisdiction_count: number;
  county_fips: Array<string>;
  source_status_counts: {
  [key: string]: {
  [key: string]: number;
};
};
  [key: string]: unknown;
};

export type PlanningSourcesEvidence = {
  comprehensive_plan?: "AVAILABLE" | "STATEWIDE_BASELINE_ONLY" | "PARTIAL" | "SOURCE_DISCOVERY_REQUIRED" | "MANUAL_REVIEW_REQUIRED" | "DATA_UNAVAILABLE" | "ERROR" | null;
  active_development?: "AVAILABLE" | "STATEWIDE_BASELINE_ONLY" | "PARTIAL" | "SOURCE_DISCOVERY_REQUIRED" | "MANUAL_REVIEW_REQUIRED" | "DATA_UNAVAILABLE" | "ERROR" | null;
  permits?: "AVAILABLE" | "STATEWIDE_BASELINE_ONLY" | "PARTIAL" | "SOURCE_DISCOVERY_REQUIRED" | "MANUAL_REVIEW_REQUIRED" | "DATA_UNAVAILABLE" | "ERROR" | null;
  [key: string]: unknown;
};

export type PlanningZoningEvidence = {
  statewide_code?: string | null;
  statewide_status?: string | null;
  local_source_status?: "AVAILABLE" | "STATEWIDE_BASELINE_ONLY" | "PARTIAL" | "SOURCE_DISCOVERY_REQUIRED" | "MANUAL_REVIEW_REQUIRED" | "DATA_UNAVAILABLE" | "ERROR" | null;
  local_source_note?: string | null;
  local_verified?: boolean;
  permitted_use_determined?: boolean;
  [key: string]: unknown;
};

export type ScopeBundle = {
  scope_id: string;
  artifacts: {
  [key: string]: ArtifactStatus;
};
  parcels: GeoJSONFeatureCollection;
  envelopes?: GeoJSONFeatureCollection | null;
  constraints?: GeoJSONFeatureCollection | null;
  site?: GeoJSONFeatureCollection | null;
  grid?: GeoJSONFeatureCollection | null;
  planning?: GeoJSONFeatureCollection | null;
  [key: string]: unknown;
};

export type SiteCandidate = {
  candidate_id: string;
  candidate_kind: string;
  candidate_score?: number | null;
  candidate_eligible?: boolean | null;
  candidate_status?: string | null;
  candidate_status_reason?: string | null;
  parcel_id?: string | null;
  assemblage_id?: string | null;
  parcel_count?: number | null;
  parcel_ids?: string | null;
  site_feasibility_class?: string | null;
  final_site_area_acres?: number | null;
  total_site_area_acres?: number | null;
  largest_contiguous_site_acres?: number | null;
  road_access_status?: string | null;
  mapped_wetland_fraction?: number | null;
  steep_slope_fraction?: number | null;
  building_reference_fraction?: number | null;
  redevelopment_burden_class?: string | null;
  [key: string]: unknown;
};

export type SiteCandidateComparisonRequest = {
  candidate_ids: Array<string>;
  [key: string]: unknown;
};

export type SiteCandidateComparisonResponse = {
  scope_id: string;
  candidates: Array<SiteCandidate>;
  [key: string]: unknown;
};

export type SiteCandidateListResponse = {
  scope_id: string;
  candidates: Array<SiteCandidate>;
  [key: string]: unknown;
};

export type SiteExistingDevelopmentEvidence = {
  building_reference_status?: string | null;
  building_reference_count?: number | null;
  building_reference_overlap_acres?: number | null;
  building_reference_fraction?: number | null;
  redevelopment_burden_class?: string | null;
  building_geometry_survey_grade?: boolean;
  [key: string]: unknown;
};

export type SiteFeasibilityEvidence = {
  site_feasibility_class?: string | null;
  site_candidate_score?: number | null;
  candidate_eligible?: boolean | null;
  candidate_status?: string | null;
  candidate_status_reason?: string | null;
  base_development_envelope_acres?: number | null;
  final_site_area_acres?: number | null;
  final_site_fraction_of_base_envelope?: number | null;
  largest_contiguous_site_acres?: number | null;
  site_component_count?: number | null;
  terrain: SiteTerrainEvidence;
  wetlands: SiteWetlandsEvidence;
  road_access: SiteRoadAccessEvidence;
  existing_development: SiteExistingDevelopmentEvidence;
  safeguards: {
  [key: string]: boolean;
};
  warning: string;
  [key: string]: unknown;
};

export type SiteRoadAccessEvidence = {
  status?: string | null;
  nearest_road_distance_m?: number | null;
  nearest_road_name?: string | null;
  nearest_road_class?: string | null;
  nearest_primary_road_distance_m?: number | null;
  nearest_accessible_road_distance_m?: number | null;
  frontage_proxy_m?: number | null;
  limited_access_adjacency_proxy_m?: number | null;
  site_envelope_to_road_distance_m?: number | null;
  legal_access_confirmed?: boolean;
  driveway_approval_confirmed?: boolean;
  [key: string]: unknown;
};

export type SiteTerrainEvidence = {
  status?: string | null;
  elevation_minimum_m?: number | null;
  elevation_maximum_m?: number | null;
  elevation_mean_m?: number | null;
  elevation_range_m?: number | null;
  slope_mean_percent?: number | null;
  slope_median_percent?: number | null;
  slope_p90_percent?: number | null;
  steep_slope_overlap_acres?: number | null;
  steep_slope_fraction?: number | null;
  severe_slope_pixel_fraction?: number | null;
  engineering_complete?: boolean;
  [key: string]: unknown;
};

export type SiteWetlandsEvidence = {
  status?: string | null;
  mapped_overlap_acres?: number | null;
  mapped_overlap_fraction?: number | null;
  special_state_concern_screening_overlap_acres?: number | null;
  field_delineation_confirmed?: boolean;
  permitting_complete?: boolean;
  [key: string]: unknown;
};

export type StatewideAuditSummary = {
  status?: string | null;
  release_status?: string | null;
  screening_shortlist_ready?: boolean | null;
  automated_recommendation_ready?: boolean;
  material_flags?: {
  [key: string]: unknown;
};
  [key: string]: unknown;
};

export type StatewideBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
  [key: string]: unknown;
};

export type StatewideCellDetailResponse = {
  cell_id: string;
  location: StatewideLocation;
  decision: StatewideDecision;
  scores: StatewideScores;
  evidence?: {
  [key: string]: {
  [key: string]: unknown;
};
};
  community_impact?: {
  [key: string]: unknown;
};
  [key: string]: unknown;
};

export type StatewideCounty = {
  fips: string;
  name: string;
  [key: string]: unknown;
};

export type StatewideDecision = {
  model_status?: string | null;
  hard_excluded: boolean;
  exclusion_reasons?: Array<string>;
  auto_screen_eligible: boolean;
  exploration_screen_eligible: boolean;
  automated_recommendation_ready: boolean;
  [key: string]: unknown;
};

export type StatewideGridSummary = {
  cell_count: number;
  complete_cells: number;
  insufficient_data_cells: number;
  hard_excluded_cells: number;
  auto_screen_eligible_cells: number;
  exploration_screen_eligible_cells: number;
  [key: string]: unknown;
};

export type StatewideHealthResponse = {
  ready: boolean;
  root: string;
  files: {
  [key: string]: {
  [key: string]: unknown;
};
};
  [key: string]: unknown;
};

export type StatewideLocation = {
  latitude?: number | null;
  longitude?: number | null;
  county_fips?: string | null;
  county_name?: string | null;
  tract_geoid?: string | null;
  land_fraction?: number | null;
  cell_area_sq_km?: number | null;
  [key: string]: unknown;
};

export type StatewideScoreBand = {
  id: string;
  label: string;
  minimum: number;
  maximum: number;
  auto_cell_count?: number | null;
  exploration_cell_count?: number | null;
  [key: string]: unknown;
};

export type StatewideScores = {
  technical_suitability?: number | null;
  effective_suitability?: number | null;
  criteria?: {
  [key: string]: number | null;
};
  [key: string]: unknown;
};

export type StatewideSummaryResponse = {
  project: string;
  analysis: string;
  model_version?: string | null;
  grid: StatewideGridSummary;
  zones?: {
  [key: string]: number;
};
  audit: StatewideAuditSummary;
  score_statistics?: {
  [key: string]: number | null;
};
  effective_score_statistics?: {
  [key: string]: number | null;
};
  score_bands?: Array<StatewideScoreBand>;
  bounds: StatewideBounds;
  counties?: Array<StatewideCounty>;
  terminology?: {
  [key: string]: unknown;
};
  required_next_stage?: Array<string>;
  [key: string]: unknown;
};

export type StatewideZoneDetailResponse = {
  zone_id: string;
  mode: string;
  properties?: {
  [key: string]: unknown;
};
  membership: ZoneMembership;
  member_summary: ZoneMemberSummary;
  interpretation: string;
  [key: string]: unknown;
};

export type SubstationSummaryEvidence = {
  feature_count?: number | null;
  known_voltage_count?: number | null;
  maximum_voltage_kv?: number | null;
  [key: string]: unknown;
};

export type TransmissionSummaryEvidence = {
  feature_count?: number | null;
  known_voltage_count?: number | null;
  maximum_voltage_kv?: number | null;
  distinct_owner_count?: number | null;
  owners?: string | null;
  [key: string]: unknown;
};

export type ValidationError = {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: {
};
};

export type ZoneMemberSummary = {
  technical_score?: {
  [key: string]: number | null;
};
  equity_gate_counts?: {
  [key: string]: number;
};
  county_counts?: {
  [key: string]: number;
};
  [key: string]: unknown;
};

export type ZoneMembership = {
  member_count: number;
  member_cell_ids?: Array<string>;
  member_cell_ids_truncated: boolean;
  [key: string]: unknown;
};
