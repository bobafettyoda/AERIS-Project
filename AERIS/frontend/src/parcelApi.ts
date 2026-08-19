import type {
  FeatureCollection,
  Geometry,
  GeoJsonProperties,
} from "geojson";

import {
  API_BASE_URL,
} from "./api";


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


export type ParcelDetail = {
  scope_id: string;
  parcel_id: string;

  identity: {
    account_id?: string | null;
    jurisdiction_code?: string | null;
    county_fips?: string | null;
    county_name?: string | null;
    property_address?: string | null;
  };

  parcel: {
    parcel_area_acres?: number | null;
    source_reported_acres?: number | null;
    geometry_area_acres?: number | null;
    land_use_code?: string | null;
    land_use_description?: string | null;
    zoning_code?: string | null;
    commercial_industrial_use?:
      string | null;
    public_water_status?:
      string | null;
    public_sewer_status?:
      string | null;
  };

  source_development_indicators:
    Record<string, unknown>;

  classification: {
    public_land_flag: boolean;
    institutional_use_flag: boolean;
    existing_development_indicator:
      boolean;
    availability_status?: string | null;
    availability_reason?: string | null;
    availability_confirmed: false;
    data_confidence?: string | null;
  };

  statewide_context: {
    cell_id?: string | null;
    technical_score?: number | null;
    effective_score?: number | null;
    equity_gate?: string | null;
    hard_excluded?: boolean | null;
    auto_eligible?: boolean | null;
    exploration_eligible?:
      boolean | null;
  };

  scope: {
    candidate_zone_id?: string | null;
    candidate_zone_mode?: string | null;
    overlap_fraction?: number | null;
    overlap_area_acres?: number | null;
    statewide_link_method?: string | null;
    statewide_context_distance_m?: number | null;
  };

  source_dates: Record<
    string,
    string | null
  >;

  warning: string;
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
