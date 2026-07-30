import type { FeatureCollection } from "geojson";


export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";


export type CandidatePoint = {
  lat: number;
  lon: number;
};


export type CriterionResult = {
  criterion?: string;
  source_layer?: string;
  methodology?: string;
  status?: string;
  excluded?: boolean | null;
  normalized_score?: number | null;
  weighted_contribution?: number | null;
  [key: string]: unknown;
};


export type SiteEvaluation = {
  analysis: string;

  input: CandidatePoint;

  study_area?: {
    name: string;
    inside_study_area: boolean | null;
    matched_boundary_count?: number;
    error?: string;
  };

  decision: {
    status: string;
    hard_excluded: boolean;
    hard_exclusion_reasons: string[];
    exclusion_checks_complete: boolean;
    provisional_ranking_eligible: boolean;
    final_ranking_eligible: boolean;
    message?: string;
  };

  score_summary: {
    configured_weight_total: number;
    scored_weight: number;
    unscored_weight: number;
    model_completion_percent: number;
    partial_weighted_score: number;
    provisional_normalized_score: number | null;
    effective_score_after_exclusions: number | null;
    final_suitability_score: number | null;
  };

  criteria: Record<string, CriterionResult>;
};


export type EquityScreenResult = {
  source_layer: string;

  input: CandidatePoint;

  tract_geoid?: string | null;

  gate_status:
    | "PASS"
    | "CAUTION"
    | "HIGH_BURDEN"
    | "INSUFFICIENT_DATA";

  auto_recommendation_eligible: boolean;
  used_in_suitability_score: boolean;
  demographic_fields_are_audit_only?: boolean;

  overburdened?: boolean;
  overburdened_factor_count?: number | null;

  underserved?: boolean;
  underserved_reasons?: string[];

  elevated_categories?: string[];

  percentiles?: {
    environmental_justice?: number | null;
    pollution_burden?: number | null;
    environmental_effects?: number | null;
    sensitive_populations?: number | null;
    underserved?: number | null;
  };

  demographic_audit?: {
    minority_or_hispanic_pct?: number | null;
    low_income_pct?: number | null;
    limited_english_pct?: number | null;
  };

  interpretation?: string;
  message?: string;
};


export async function evaluateCandidateSite(
  point: CandidatePoint,
  signal?: AbortSignal,
): Promise<SiteEvaluation> {
  const parameters = new URLSearchParams({
    lat: point.lat.toString(),
    lon: point.lon.toString(),
  });

  const response = await fetch(
    `${API_BASE_URL}/analysis/` +
      `data-center-demo/candidate-site?${parameters}`,
    {
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      `AERIS backend returned HTTP ${response.status}.`,
    );
  }

  return (await response.json()) as SiteEvaluation;
}


export async function evaluateEquityScreen(
  point: CandidatePoint,
  signal?: AbortSignal,
): Promise<EquityScreenResult> {
  const parameters = new URLSearchParams({
    lat: point.lat.toString(),
    lon: point.lon.toString(),
  });

  const response = await fetch(
    `${API_BASE_URL}/analysis/` +
      `data-center-demo/equity-screen?${parameters}`,
    {
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      `Equity screen returned HTTP ${response.status}.`,
    );
  }

  return (await response.json()) as EquityScreenResult;
}


export async function fetchMarylandBoundary(
  signal?: AbortSignal,
): Promise<FeatureCollection> {
  const response = await fetch(
    `${API_BASE_URL}/gis/study-area/maryland`,
    {
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      "Maryland boundary could not be loaded.",
    );
  }

  return (await response.json()) as FeatureCollection;
}
