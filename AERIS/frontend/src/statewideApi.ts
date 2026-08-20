import type {
  FeatureCollection,
  Geometry,
  GeoJsonProperties,
} from "geojson";

import {
  API_BASE_URL,
} from "./api";

import type {
  StatewideCellDetailResponse,
  StatewideSummaryResponse,
  StatewideZoneDetailResponse,
} from "./generated/api";


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


export type StatewideSummary = StatewideSummaryResponse;


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


export type StatewideCellDetail = StatewideCellDetailResponse;


export type StatewideZoneDetail = StatewideZoneDetailResponse;


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
