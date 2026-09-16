import { API_BASE_URL } from "./api";


export type ViabilityCandidate = {
  candidate_id: string;
  candidate_kind: string;
  parcel_id?: string | null;
  assemblage_id?: string | null;
  parcel_count?: number | null;
  parcel_ids?: string | null;
  candidate_score?: number | null;
  viability_score?: number | null;
  viability_status: string;
  comparison_eligible: boolean;
  rejection_reasons: string[];
  hold_reasons: string[];
  review_reasons: string[];
  site_feasibility_class?: string | null;
  final_site_area_acres?: number | null;
  total_site_area_acres?: number | null;
  largest_contiguous_site_acres?: number | null;
  road_access_status?: string | null;
  mapped_wetland_fraction?: number | null;
  steep_slope_fraction?: number | null;
  building_reference_fraction?: number | null;
  redevelopment_burden_class?: string | null;
  regional_technical_score?: number | null;
  regional_effective_score?: number | null;
  grid_context_class?: string | null;
  grid_data_confidence?: string | null;
  capacity_status?: string | null;
  planning_review_status?: string | null;
  planning_data_confidence?: string | null;
  availability_confirmed?: boolean | null;
};


export type ViabilityScopeEvaluation = {
  scope_id: string;
  scope_status: string;
  artifact_readiness: Record<string, boolean>;
  missing_artifacts: string[];
  counts: {
    evaluated: number;
    comparison_eligible: number;
    evidence_hold: number;
    rejected: number;
  };
  rejection_reason_counts: Record<string, number>;
  hold_reason_counts: Record<string, number>;
  review_reason_counts: Record<string, number>;
  comparison_candidates: ViabilityCandidate[];
  safeguards: Record<string, boolean>;
  interpretation?: Record<string, unknown>;
};


async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `Viability API returned HTTP ${response.status}: ${text.slice(0, 400)}`,
    );
  }
  return (await response.json()) as T;
}


async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `Viability API returned HTTP ${response.status}: ${text.slice(0, 400)}`,
    );
  }
  return (await response.json()) as T;
}


export async function fetchViabilityScope(
  scopeId: string,
): Promise<ViabilityScopeEvaluation> {
  return fetchJson<ViabilityScopeEvaluation>(
    `/analysis/viability/scopes/${encodeURIComponent(scopeId)}`,
  );
}


export async function compareViabilityCandidates(
  scopeId: string,
  candidateIds: string[],
): Promise<ViabilityCandidate[]> {
  const payload = await postJson<{
    scope_id: string;
    candidates: ViabilityCandidate[];
  }>(
    `/analysis/viability/scopes/${encodeURIComponent(scopeId)}/compare`,
    { candidate_ids: candidateIds },
  );
  return payload.candidates;
}
