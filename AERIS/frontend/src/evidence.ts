import type { CriterionResult } from "./api";


export type EvidenceRow = {
  label: string;
  value: string;
};


type UnknownRecord = Record<string, unknown>;


function asRecord(
  value: unknown,
): UnknownRecord | null {
  if (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  ) {
    return value as UnknownRecord;
  }

  return null;
}


function readPath(
  source: unknown,
  path: string[],
): unknown {
  let current: unknown = source;

  for (const key of path) {
    const record = asRecord(current);

    if (!record) {
      return undefined;
    }

    current = record[key];
  }

  return current;
}


function numberAt(
  source: unknown,
  ...path: string[]
): number | null {
  const value = readPath(source, path);

  return typeof value === "number"
    ? value
    : null;
}


function stringAt(
  source: unknown,
  ...path: string[]
): string | null {
  const value = readPath(source, path);

  return typeof value === "string"
    ? value
    : null;
}


function booleanAt(
  source: unknown,
  ...path: string[]
): boolean | null {
  const value = readPath(source, path);

  return typeof value === "boolean"
    ? value
    : null;
}


function formatDistance(
  value: number | null,
): string {
  if (value === null) {
    return "Not available";
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} km`;
  }

  return `${Math.round(value)} m`;
}


function formatNumber(
  value: number | null,
  digits = 0,
): string {
  if (value === null) {
    return "Not available";
  }

  return value.toLocaleString(
    undefined,
    {
      maximumFractionDigits: digits,
    },
  );
}


function formatPercentScore(
  value: number | null,
): string {
  if (value === null) {
    return "Not available";
  }

  return `${Math.round(value * 100)}%`;
}


function formatModelWeight(
  value: number | null,
): string {
  if (value === null) {
    return "Not available";
  }

  return `${(value * 100).toFixed(1)}%`;
}


function yesNo(
  value: boolean | null,
): string {
  if (value === null) {
    return "Not available";
  }

  return value ? "Yes" : "No";
}


function commonRows(
  criterion: CriterionResult,
): EvidenceRow[] {
  return [
    {
      label: "Model weight",
      value: formatModelWeight(
        numberAt(criterion, "weight"),
      ),
    },
    {
      label: "Weighted contribution",
      value: formatNumber(
        numberAt(
          criterion,
          "weighted_contribution",
        ),
        4,
      ),
    },
  ];
}


export function evidenceRows(
  criterionName: string,
  criterion: CriterionResult,
): EvidenceRow[] {
  let rows: EvidenceRow[] = [];

  switch (criterionName) {
    case "climate":
      rows = [
        {
          label: "Annual mean temperature",
          value: `${
            formatNumber(
              numberAt(
                criterion,
                "temperature_c",
                "annual_mean",
              ),
              1,
            )
          } °C`,
        },
        {
          label: "July mean temperature",
          value: `${
            formatNumber(
              numberAt(
                criterion,
                "temperature_c",
                "july_mean",
              ),
              1,
            )
          } °C`,
        },
        {
          label: "Annual temperature score",
          value: formatPercentScore(
            numberAt(
              criterion,
              "component_scores",
              "annual_mean_temperature",
              "score",
            ),
          ),
        },
        {
          label: "July temperature score",
          value: formatPercentScore(
            numberAt(
              criterion,
              "component_scores",
              "july_mean_temperature",
              "score",
            ),
          ),
        },
      ];
      break;

    case "grid_infrastructure":
      rows = [
        {
          label: "Nearest substation",
          value: formatDistance(
            numberAt(
              criterion,
              "components",
              "substation_proximity",
              "nearest_distance_m",
            ),
          ),
        },
        {
          label: "Substation component",
          value: formatPercentScore(
            numberAt(
              criterion,
              "components",
              "substation_proximity",
              "normalized_score",
            ),
          ),
        },
        {
          label: "Nearest transmission line",
          value: formatDistance(
            numberAt(
              criterion,
              "components",
              "transmission_line_proximity",
              "nearest_distance_m",
            ),
          ),
        },
        {
          label: "Transmission component",
          value: formatPercentScore(
            numberAt(
              criterion,
              "components",
              "transmission_line_proximity",
              "normalized_score",
            ),
          ),
        },
      ];
      break;

    case "telecom_infrastructure":
      rows = [
        {
          label: "Direct reported coverage",
          value: yesNo(
            booleanAt(
              criterion,
              "direct_reported_coverage",
            ),
          ),
        },
        {
          label: "Nearest reported coverage",
          value: formatDistance(
            numberAt(
              criterion,
              "nearest_reported_coverage_m",
            ),
          ),
        },
        {
          label: "Distinct providers",
          value: formatNumber(
            numberAt(
              criterion,
              "distinct_provider_count",
            ),
          ),
        },
        {
          label: "Provider-diversity score",
          value: formatPercentScore(
            numberAt(
              criterion,
              "component_scores",
              "provider_diversity",
              "score",
            ),
          ),
        },
      ];
      break;

    case "protected_areas":
      rows = [
        {
          label: "Inside protected area",
          value: yesNo(
            booleanAt(
              criterion,
              "inside_protected_area",
            ),
          ),
        },
        {
          label: "Protected layers checked",
          value: formatNumber(
            numberAt(
              criterion,
              "layers_checked",
            ),
          ),
        },
        {
          label: "Matched protected layers",
          value: formatNumber(
            numberAt(
              criterion,
              "matched_layer_count",
            ),
          ),
        },
      ];
      break;

    case "water_bodies":
      rows = [
        {
          label: "Nearest surface water",
          value: formatDistance(
            numberAt(
              criterion,
              "nearest_surface_water_m",
            ),
          ),
        },
        {
          label: "Nearest stream",
          value: formatDistance(
            numberAt(
              criterion,
              "nearest_stream_m",
            ),
          ),
        },
        {
          label: "Nearest lake",
          value: formatDistance(
            numberAt(
              criterion,
              "nearest_lake_m",
            ),
          ),
        },
        {
          label: "Inside mapped water",
          value: yesNo(
            booleanAt(
              criterion,
              "inside_waterbody",
            ),
          ),
        },
      ];
      break;

    case "population_density":
      rows = [
        {
          label: "Census tract",
          value:
            stringAt(
              criterion,
              "tract",
              "name",
            ) ?? "Not available",
        },
        {
          label: "Tract population",
          value: formatNumber(
            numberAt(
              criterion,
              "population",
            ),
          ),
        },
        {
          label: "Population density",
          value: `${
            formatNumber(
              numberAt(
                criterion,
                "density_people_sq_km",
              ),
              0,
            )
          } people/km²`,
        },
        {
          label: "Land area",
          value: `${
            formatNumber(
              numberAt(
                criterion,
                "land_area_sq_km",
              ),
              2,
            )
          } km²`,
        },
      ];
      break;

    case "road_access":
      rows = [
        {
          label: "Nearest mapped road",
          value: formatDistance(
            numberAt(
              criterion,
              "nearest_distance_m",
            ),
          ),
        },
        {
          label: "Road features checked",
          value: formatNumber(
            numberAt(
              criterion,
              "features_checked",
            ),
          ),
        },
        {
          label: "Preferred distance",
          value: formatDistance(
            numberAt(
              criterion,
              "normalization",
              "best_m",
            ),
          ),
        },
        {
          label: "Lowest-scoring distance",
          value: formatDistance(
            numberAt(
              criterion,
              "normalization",
              "worst_m",
            ),
          ),
        },
      ];
      break;

    case "hydro_hazard":
      rows = [
        {
          label: "Inside mapped flood polygon",
          value: yesNo(
            booleanAt(
              criterion,
              "inside_mapped_flood_polygon",
            ),
          ),
        },
        {
          label: "Inside special flood hazard area",
          value: yesNo(
            booleanAt(
              criterion,
              "inside_sfha",
            ),
          ),
        },
        {
          label: "Within flood buffer",
          value: yesNo(
            booleanAt(
              criterion,
              "within_sfha_buffer",
            ),
          ),
        },
        {
          label: "Flood buffer",
          value: formatDistance(
            numberAt(
              criterion,
              "sfha_buffer_m",
            ),
          ),
        },
      ];
      break;
  }

  return [
    ...rows,
    ...commonRows(criterion),
  ];
}


export function criterionLimitations(
  criterion: CriterionResult,
): string[] {
  const value = readPath(
    criterion,
    ["limitations"],
  );

  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(
    (item): item is string =>
      typeof item === "string",
  );
}
