import type {
  FeatureCollection,
} from "geojson";

import type {
  Map as MapLibreMap,
} from "maplibre-gl";


export function addParcelMapLayers(
  map: MapLibreMap,
  emptyCollection: FeatureCollection,
): void {
  map.addSource(
    "parcel-zones",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addSource(
    "parcel-polygons",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addSource(
    "parcel-envelopes",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addSource(
    "parcel-constraints",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addSource(
    "parcel-grid-evidence",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addSource(
    "parcel-planning-evidence",
    {
      type: "geojson",
      data: emptyCollection,
    },
  );

  map.addLayer({
    id: "parcel-zone-fill",
    type: "fill",
    source: "parcel-zones",
    paint: {
      "fill-color": "#7c3aed",
      "fill-opacity": 0.12,
    },
  });

  map.addLayer({
    id: "parcel-zone-line",
    type: "line",
    source: "parcel-zones",
    paint: {
      "line-color": "#6d28d9",
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        8,
        3,
        14,
        5,
      ],
    },
  });

  map.addLayer({
    id: "parcel-fill",
    type: "fill",
    source: "parcel-polygons",
    paint: {
      "fill-color": [
        "match",
        [
          "get",
          "availability_status",
        ],
        "PUBLIC_OR_INSTITUTIONAL",
        "#be123c",
        "EXISTING_USE_REVIEW_REQUIRED",
        "#d97706",
        "POTENTIAL_FURTHER_REVIEW",
        "#15803d",
        "DATA_INSUFFICIENT",
        "#64748b",
        "#64748b",
      ],
      "fill-opacity": [
        "interpolate",
        ["linear"],
        [
          "coalesce",
          [
            "get",
            "scope_overlap_fraction",
          ],
          0,
        ],
        0,
        0.05,
        0.05,
        0.10,
        0.25,
        0.20,
        0.50,
        0.30,
        1,
        0.42,
      ],
    },
  });

  map.addLayer({
    id: "parcel-line",
    type: "line",
    source: "parcel-polygons",
    paint: {
      "line-color": [
        "match",
        [
          "get",
          "availability_status",
        ],
        "PUBLIC_OR_INSTITUTIONAL",
        "#9f1239",
        "EXISTING_USE_REVIEW_REQUIRED",
        "#b45309",
        "POTENTIAL_FURTHER_REVIEW",
        "#166534",
        "#475569",
      ],
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        10,
        0.45,
        16,
        2.2,
      ],

      "line-opacity": [
        "interpolate",
        ["linear"],
        [
          "coalesce",
          [
            "get",
            "scope_overlap_fraction",
          ],
          0,
        ],
        0,
        0.10,
        0.05,
        0.20,
        0.25,
        0.55,
        0.50,
        0.78,
        1,
        1,
      ],
    },
  });

  map.addLayer({
    id: "parcel-constraint-fill",
    type: "fill",
    source: "parcel-constraints",
    layout: {
      visibility: "none",
    },
    paint: {
      "fill-color": [
        "match",
        ["get", "constraint_id"],
        "water",
        "#2563eb",
        "protected_lands",
        "#166534",
        "sfha",
        "#0891b2",
        "aviation",
        "#dc2626",
        "aviation_review",
        "#7c3aed",
        "#64748b",
      ],
      "fill-opacity": 0.45,
    },
  });

  map.addLayer({
    id: "parcel-envelope-fill",
    type: "fill",
    source: "parcel-envelopes",
    layout: {
      visibility: "none",
    },
    paint: {
      "fill-color": "#0f766e",
      "fill-opacity": 0.48,
    },
  });

  map.addLayer({
    id: "parcel-envelope-line",
    type: "line",
    source: "parcel-envelopes",
    layout: {
      visibility: "none",
    },
    paint: {
      "line-color": "#064e3b",
      "line-width": 1.8,
    },
  });

  map.addLayer({
    id: "parcel-grid-transmission",
    type: "line",
    source: "parcel-grid-evidence",
    filter: [
      "==",
      ["get", "evidence_kind"],
      "TRANSMISSION_LINE",
    ],
    layout: {
      visibility: "none",
    },
    paint: {
      "line-color": [
        "match",
        [
          "get",
          "transmission_voltage_class",
        ],
        "EXTRA_HIGH_345_KV_PLUS",
        "#7c3aed",
        "HIGH_230_TO_344_KV",
        "#dc2626",
        "REGIONAL_115_TO_229_KV",
        "#ea580c",
        "SUBTRANSMISSION_69_TO_114_KV",
        "#ca8a04",
        "BELOW_69_KV",
        "#65a30d",
        "#64748b",
      ],
      "line-width": [
        "interpolate",
        ["linear"],
        [
          "coalesce",
          [
            "get",
            "transmission_voltage_kv",
          ],
          69,
        ],
        69,
        1.5,
        115,
        2.25,
        230,
        3.25,
        345,
        4.25,
        500,
        5.25,
      ],
      "line-opacity": 0.9,
    },
  });

  map.addLayer({
    id: "parcel-grid-substations",
    type: "circle",
    source: "parcel-grid-evidence",
    filter: [
      "==",
      ["get", "evidence_kind"],
      "SUBSTATION",
    ],
    layout: {
      visibility: "none",
    },
    paint: {
      "circle-radius": [
        "interpolate",
        ["linear"],
        [
          "coalesce",
          [
            "get",
            "substation_max_voltage_kv",
          ],
          69,
        ],
        69,
        6,
        115,
        8,
        230,
        10,
        500,
        13,
      ],
      "circle-color": "#1d4ed8",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.2,
      "circle-opacity": 0.92,
    },
  });

  map.addLayer({
    id: "parcel-planning-fill",
    type: "fill",
    source: "parcel-planning-evidence",
    layout: {
      visibility: "none",
    },
    paint: {
      "fill-color": [
        "match",
        [
          "get",
          "planning_context_kind",
        ],
        "priority_funding_area",
        "#2563eb",
        "critical_area",
        "#dc2626",
        "enterprise_zone",
        "#7c3aed",
        "sustainable_community",
        "#059669",
        "foreign_trade_zone",
        "#0891b2",
        "rise_zone",
        "#d97706",
        "opportunity_zone",
        "#9333ea",
        "municipal_boundary",
        "#ca8a04",
        "#64748b",
      ],
      "fill-opacity": [
        "match",
        [
          "get",
          "planning_context_kind",
        ],
        "municipal_boundary",
        0.08,
        0.28,
      ],
    },
  });

  map.addLayer({
    id: "parcel-planning-line",
    type: "line",
    source: "parcel-planning-evidence",
    layout: {
      visibility: "none",
    },
    paint: {
      "line-color": [
        "match",
        [
          "get",
          "planning_context_kind",
        ],
        "municipal_boundary",
        "#ca8a04",
        "critical_area",
        "#dc2626",
        "#6d28d9",
      ],
      "line-width": [
        "match",
        [
          "get",
          "planning_context_kind",
        ],
        "municipal_boundary",
        2.5,
        1.5,
      ],
      "line-opacity": 0.85,
    },
  });

  map.moveLayer(
    "parcel-zone-fill"
  );

  map.moveLayer(
    "parcel-grid-transmission"
  );

  map.moveLayer(
    "parcel-grid-substations"
  );

  map.moveLayer(
    "parcel-zone-line"
  );
}
