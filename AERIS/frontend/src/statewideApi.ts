import type {
  FeatureCollection,
  Geometry,
  GeoJsonProperties,
} from "geojson";

import {
  API_BASE_URL,
} from "./api";


export type StatewideScoreType =
  | "technical"
  | "effective";


export type StatewideEligibility =
  | "all"
  | "auto"
  | "exploration";


export type StatewideZoneMode =
  | "top"
  | "auto"
  | "exploration";


export type StatewideFilterState = {
  scoreType: StatewideScoreType;
  minimumScore: number;
  maximumScore: number;
  eligibility: StatewideEligibility;
  equityGate: string;
  county: string;
  excluded: "all" | "true" | "false";
};


export type StatewideSummary = {
  project: string;
  analysis: string;
  model_version?: string;

  grid: {
    cell_count: number;
    complete_cells: number;
    insufficient_data_cells: number;
    hard_excluded_cells: number;
    auto_screen_eligible_cells: number;
    exploration_screen_eligible_cells: number;
  };

  zones: Record<string, number>;

  audit: {
    status: string;
    release_status: string;
    screening_shortlist_ready: boolean;
    automated_recommendation_ready: boolean;
    material_flags: Record<string, unknown>;
  };

  score_statistics: Record<
    string,
    number | null
  >;

  effective_score_statistics: Record<
    string,
    number | null
  >;

  score_bands: Array<{
    id: string;
    label: string;
    minimum: number;
    maximum: number;
    auto_cell_count?: number;
    exploration_cell_count?: number;
  }>;

  bounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  };

  counties: Array<{
    fips: string;
    name: string;
  }>;

  terminology: Record<string, unknown>;
  required_next_stage: string[];
};


export type StatewideFeatureCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata?: Record<
      string,
      unknown
    >;
  };


export type StatewideCellDetail = {
  cell_id: string;

  location: {
    latitude?: number | null;
    longitude?: number | null;
    county_fips?: string | null;
    county_name?: string | null;
    tract_geoid?: string | null;
    land_fraction?: number | null;
    cell_area_sq_km?: number | null;
  };

  decision: {
    model_status?: string | null;
    hard_excluded: boolean;
    exclusion_reasons: string[];
    auto_screen_eligible: boolean;
    exploration_screen_eligible: boolean;
    automated_recommendation_ready: boolean;
  };

  scores: {
    technical_suitability?: number | null;
    effective_suitability?: number | null;
    criteria: Record<
      string,
      number | null
    >;
  };

  evidence: Record<
    string,
    Record<string, unknown>
  >;

  community_impact: Record<
    string,
    unknown
  >;
};


export type StatewideZoneDetail = {
  zone_id: string;
  mode: string;

  properties: Record<
    string,
    unknown
  >;

  membership: {
    member_count: number;
    member_cell_ids: string[];
    member_cell_ids_truncated: boolean;
  };

  member_summary: {
    technical_score: Record<
      string,
      number | null
    >;

    equity_gate_counts: Record<
      string,
      number
    >;

    county_counts: Record<
      string,
      number
    >;
  };

  interpretation: string;
};


async function fetchJson<T>(
  path: string,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
  );

  if (!response.ok) {
    const text = await response.text();

    throw new Error(
      (
        `Statewide API returned ` +
        `HTTP ${response.status}: ` +
        text.slice(0, 300)
      ),
    );
  }

  return (await response.json()) as T;
}


export async function fetchStatewideSummary():
Promise<StatewideSummary> {
  return fetchJson<StatewideSummary>(
    "/analysis/statewide/summary",
  );
}


export async function fetchStatewideGrid(
  filters: StatewideFilterState,
): Promise<StatewideFeatureCollection> {
  const parameters =
    new URLSearchParams({
      score_type: filters.scoreType,
      minimum_score:
        filters.minimumScore.toString(),
      maximum_score:
        filters.maximumScore.toString(),
      eligibility:
        filters.eligibility,
      limit: "30000",
    });

  if (filters.equityGate) {
    parameters.set(
      "equity_gate",
      filters.equityGate,
    );
  }

  if (filters.county) {
    parameters.set(
      "county",
      filters.county,
    );
  }

  if (filters.excluded !== "all") {
    parameters.set(
      "excluded",
      filters.excluded,
    );
  }

  return fetchJson<StatewideFeatureCollection>(
    (
      "/analysis/statewide/grid?"
      + parameters.toString()
    ),
  );
}


export async function fetchStatewideZones(
  mode: StatewideZoneMode,
): Promise<StatewideFeatureCollection> {
  const parameters =
    new URLSearchParams({
      mode,
    });

  if (mode === "top") {
    parameters.set(
      "top_n",
      "5",
    );
  }

  return fetchJson<StatewideFeatureCollection>(
    (
      "/analysis/statewide/"
      + "candidate-zones?"
      + parameters.toString()
    ),
  );
}


export async function fetchStatewideCell(
  cellId: string,
): Promise<StatewideCellDetail> {
  return fetchJson<StatewideCellDetail>(
    (
      "/analysis/statewide/cells/"
      + encodeURIComponent(cellId)
    ),
  );
}


export async function fetchStatewideZone(
  zoneId: string,
): Promise<StatewideZoneDetail> {
  return fetchJson<StatewideZoneDetail>(
    (
      "/analysis/statewide/zones/"
      + encodeURIComponent(zoneId)
    ),
  );
}
