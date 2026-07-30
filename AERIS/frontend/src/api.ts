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
};

export type SiteEvaluation = {
  analysis: string;
  input: CandidatePoint;
  decision: {
    status: string;
    hard_excluded: boolean;
    hard_exclusion_reasons: string[];
    exclusion_checks_complete: boolean;
    provisional_ranking_eligible: boolean;
    final_ranking_eligible: boolean;
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

export async function evaluateCandidateSite(
  point: CandidatePoint,
  signal?: AbortSignal,
): Promise<SiteEvaluation> {
  const parameters = new URLSearchParams({
    lat: point.lat.toString(),
    lon: point.lon.toString(),
  });

  const response = await fetch(
    `${API_BASE_URL}/analysis/data-center-demo/candidate-site?${parameters}`,
    { signal },
  );

  if (!response.ok) {
    throw new Error(
      `AERIS backend returned HTTP ${response.status}.`,
    );
  }

  return (await response.json()) as SiteEvaluation;
}
