import type {
  FeatureCollection,
  Geometry,
  GeoJsonProperties,
} from "geojson";

import {
  API_BASE_URL,
} from "./api";

import type {
  ArtifactStatus as GeneratedArtifactStatus,
  BuildJob as GeneratedBuildJob,
  ParcelDetailResponse as GeneratedParcelDetail,
  SiteCandidate as GeneratedSiteCandidate,
} from "./generated/api";


export type ParcelFeatureCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata: {
      scope: {
        scope_id: string;
        scope_type: string;
        label: string;
        zone_id?: string | null;
      };

      matching_count: number;
      returned_count: number;
      truncated: boolean;

      availability_status_counts:
        Record<string, number>;

      safeguards:
        Record<string, boolean>;
    };
  };


export type ParcelDetail =
  GeneratedParcelDetail;


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
        `Parcel API returned HTTP `
        + `${response.status}: `
        + text.slice(0, 400)
      ),
    );
  }

  return (await response.json()) as T;
}


export async function fetchZoneParcels(
  zoneId: string,
): Promise<ParcelFeatureCollection> {
  return fetchJson<ParcelFeatureCollection>(
    (
      "/analysis/parcels/zone/"
      + encodeURIComponent(zoneId)
    ),
  );
}


export async function fetchBboxParcels(
  west: number,
  south: number,
  east: number,
  north: number,
  scopeName: string,
): Promise<ParcelFeatureCollection> {
  const parameters =
    new URLSearchParams({
      west: west.toString(),
      south: south.toString(),
      east: east.toString(),
      north: north.toString(),
      scope_name: scopeName,
    });

  return fetchJson<ParcelFeatureCollection>(
    (
      "/analysis/parcels/bbox?"
      + parameters.toString()
    ),
  );
}


export async function fetchParcelDetail(
  scopeId: string,
  parcelId: string,
): Promise<ParcelDetail> {
  return fetchJson<ParcelDetail>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/parcels/"
      + encodeURIComponent(parcelId)
    ),
  );
}


export type ParcelEnvelopeCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata: {
      scope_id: string;
      layer: string;
      returned_count: number;

      manifest: {
        counts: Record<
          string,
          number
        >;

        status_counts: Record<
          string,
          number
        >;

        statistics?: Record<
          string,
          unknown
        >;

        constraints?: Record<
          string,
          unknown
        >;

        safeguards: Record<
          string,
          boolean
        >;

        interpretation?: Record<
          string,
          unknown
        >;
      };
    };
  };


export async function fetchParcelEnvelopes(
  scopeId: string,
): Promise<ParcelEnvelopeCollection> {
  return fetchJson<ParcelEnvelopeCollection>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/development-envelopes"
    ),
  );
}


export async function fetchParcelConstraints(
  scopeId: string,
): Promise<ParcelEnvelopeCollection> {
  return fetchJson<ParcelEnvelopeCollection>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/constraints"
    ),
  );
}


export type ParcelGridEvidenceCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata: {
      scope_id: string;
      returned_count: number;

      counts: Record<
        string,
        number
      >;

      context_class_counts:
        Record<string, number>;

      safeguards: {
        capacity_status: string;
        available_capacity_mw: null;
        capacity_inferred_from_voltage:
          false;
        capacity_inferred_from_distance:
          false;
        utility_confirmation_required:
          true;
        interconnection_study_required:
          true;
        electrical_service_feasibility_confirmed:
          false;
      };

      interpretation:
        Record<string, unknown>;
    };
  };


export async function fetchParcelGridEvidence(
  scopeId: string,
): Promise<ParcelGridEvidenceCollection> {
  return fetchJson<ParcelGridEvidenceCollection>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/grid-evidence"
    ),
  );
}


export type ParcelPlanningEvidenceCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata: {
      scope_id: string;
      returned_count: number;

      counts: Record<
        string,
        number
      >;

      planning_review_status_counts:
        Record<string, number>;

      registry_coverage: {
        jurisdiction_count: number;
      };

      safeguards: Record<
        string,
        boolean
      >;
    };
  };


export async function fetchParcelPlanningEvidence(
  scopeId: string,
): Promise<ParcelPlanningEvidenceCollection> {
  return fetchJson<ParcelPlanningEvidenceCollection>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/planning-evidence"
    ),
  );
}


export type SiteCandidate = GeneratedSiteCandidate;


export type ParcelSiteEvidenceCollection =
  FeatureCollection<
    Geometry,
    GeoJsonProperties
  > & {
    metadata: {
      scope_id: string;
      returned_count: number;
      counts: Record<string, number>;
      domain_status: Record<
        string,
        {
          state: string;
          error?: string | null;
        }
      >;
      site_feasibility_class_counts:
        Record<string, number>;
      top_candidates: SiteCandidate[];
      safeguards: Record<string, boolean>;
      interpretation: Record<string, unknown>;
    };
  };


export async function fetchParcelSiteEvidence(
  scopeId: string,
): Promise<ParcelSiteEvidenceCollection> {
  return fetchJson<ParcelSiteEvidenceCollection>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/site-evidence"
    ),
  );
}


export async function fetchSiteCandidates(
  scopeId: string,
  limit = 25,
): Promise<SiteCandidate[]> {
  const payload = await fetchJson<{
    scope_id: string;
    candidates: SiteCandidate[];
  }>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/site-candidates?limit="
      + encodeURIComponent(limit.toString())
    ),
  );

  return payload.candidates;
}


export async function compareSiteCandidates(
  scopeId: string,
  candidateIds: string[],
): Promise<SiteCandidate[]> {
  const payload = await postJson<{
    scope_id: string;
    candidates: SiteCandidate[];
  }>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/compare-site-candidates"
    ),
    {
      candidate_ids: candidateIds,
    },
  );

  return payload.candidates;
}


export type ArtifactStatus =
  GeneratedArtifactStatus;


export type ParcelBuildJob =
  GeneratedBuildJob;


export type ParcelScopeBundle = {
  scope_id: string;
  artifacts: Record<string, ArtifactStatus>;
  parcels: ParcelFeatureCollection;
  envelopes: ParcelEnvelopeCollection | null;
  constraints: ParcelEnvelopeCollection | null;
  site: ParcelSiteEvidenceCollection | null;
  grid: ParcelGridEvidenceCollection | null;
  planning: ParcelPlanningEvidenceCollection | null;
};


async function postJson<T>(
  path: string,
  body: unknown,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
  );

  if (!response.ok) {
    const text = await response.text();

    throw new Error(
      (
        `Parcel API returned HTTP `
        + `${response.status}: `
        + text.slice(0, 400)
      ),
    );
  }

  return (await response.json()) as T;
}


export async function startZoneParcelBuild(
  zoneId: string,
  refresh = false,
): Promise<ParcelBuildJob> {
  return postJson<ParcelBuildJob>(
    (
      "/analysis/parcels/build/zone/"
      + encodeURIComponent(zoneId)
    ),
    {
      refresh,
    },
  );
}


export async function fetchParcelBuildJob(
  jobId: string,
): Promise<ParcelBuildJob> {
  return fetchJson<ParcelBuildJob>(
    (
      "/analysis/parcels/jobs/"
      + encodeURIComponent(jobId)
    ),
  );
}


export async function fetchParcelScopeBundle(
  scopeId: string,
): Promise<ParcelScopeBundle> {
  return fetchJson<ParcelScopeBundle>(
    (
      "/analysis/parcels/scopes/"
      + encodeURIComponent(scopeId)
      + "/bundle"
    ),
  );
}
