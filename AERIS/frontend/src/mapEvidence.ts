import type { FeatureCollection } from "geojson";
import * as maplibregl from "maplibre-gl";

import type { SiteMapEvidence } from "./api";


export type EvidenceGroup =
  | "roads"
  | "grid"
  | "water"
  | "flood"
  | "protected";


export type EvidenceVisibility = Record<
  EvidenceGroup,
  boolean
>;


export const DEFAULT_VISIBILITY: EvidenceVisibility = {
  roads: true,
  grid: true,
  water: true,
  flood: false,
  protected: false,
};


export const EVIDENCE_GROUPS: Array<{
  key: EvidenceGroup;
  label: string;
  description: string;
}> = [
  {
    key: "roads",
    label: "Road evidence",
    description:
      "Nearby roads and the selected nearest segment",
  },
  {
    key: "grid",
    label: "Power infrastructure",
    description:
      "Transmission lines and substations",
  },
  {
    key: "water",
    label: "Surface water",
    description:
      "Streams, lakes, and nearest features",
  },
  {
    key: "flood",
    label: "Flood context",
    description:
      "Mapped FEMA floodplain features",
  },
  {
    key: "protected",
    label: "Protected lands",
    description:
      "Protected-area context near the site",
  },
];


const EMPTY: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};


const GROUP_LAYERS: Record<
  EvidenceGroup,
  string[]
> = {
  roads: [
    "aeris-road-context",
    "aeris-road-nearest",
    "aeris-road-connector",
  ],

  grid: [
    "aeris-transmission-context",
    "aeris-transmission-nearest",
    "aeris-transmission-connector",
    "aeris-substation-context",
    "aeris-substation-nearest",
    "aeris-substation-connector",
  ],

  water: [
    "aeris-stream-context",
    "aeris-stream-nearest",
    "aeris-stream-connector",
    "aeris-lake-context-fill",
    "aeris-lake-context-line",
    "aeris-lake-nearest-fill",
    "aeris-lake-nearest-line",
    "aeris-lake-connector",
  ],

  flood: [
    "aeris-flood-fill",
    "aeris-flood-line",
  ],

  protected: [
    "aeris-protected-fill",
    "aeris-protected-line",
  ],
};


function addGeoJsonSource(
  map: maplibregl.Map,
  id: string,
): void {
  if (map.getSource(id)) {
    return;
  }

  map.addSource(id, {
    type: "geojson",
    data: EMPTY,
  });
}


function addLineLayer(
  map: maplibregl.Map,
  id: string,
  source: string,
  paint: maplibregl.LineLayerSpecification["paint"],
): void {
  if (map.getLayer(id)) {
    return;
  }

  map.addLayer({
    id,
    type: "line",
    source,
    paint,
  });
}


function addCircleLayer(
  map: maplibregl.Map,
  id: string,
  source: string,
  paint: maplibregl.CircleLayerSpecification["paint"],
): void {
  if (map.getLayer(id)) {
    return;
  }

  map.addLayer({
    id,
    type: "circle",
    source,
    paint,
  });
}


function addFillLayer(
  map: maplibregl.Map,
  id: string,
  source: string,
  paint: maplibregl.FillLayerSpecification["paint"],
): void {
  if (map.getLayer(id)) {
    return;
  }

  map.addLayer({
    id,
    type: "fill",
    source,
    paint,
  });
}


export function addEvidenceLayers(
  map: maplibregl.Map,
): void {
  const sourceIds = [
    "aeris-road-context-source",
    "aeris-road-nearest-source",
    "aeris-road-connector-source",

    "aeris-transmission-context-source",
    "aeris-transmission-nearest-source",
    "aeris-transmission-connector-source",

    "aeris-substation-context-source",
    "aeris-substation-nearest-source",
    "aeris-substation-connector-source",

    "aeris-stream-context-source",
    "aeris-stream-nearest-source",
    "aeris-stream-connector-source",

    "aeris-lake-context-source",
    "aeris-lake-nearest-source",
    "aeris-lake-connector-source",

    "aeris-flood-source",
    "aeris-protected-source",
  ];

  sourceIds.forEach((sourceId) => {
    addGeoJsonSource(map, sourceId);
  });

  addLineLayer(
    map,
    "aeris-road-context",
    "aeris-road-context-source",
    {
      "line-color": "#687986",
      "line-width": 1.4,
      "line-opacity": 0.48,
    },
  );

  addLineLayer(
    map,
    "aeris-road-nearest",
    "aeris-road-nearest-source",
    {
      "line-color": "#e87916",
      "line-width": 5,
      "line-opacity": 1,
    },
  );

  addLineLayer(
    map,
    "aeris-road-connector",
    "aeris-road-connector-source",
    {
      "line-color": "#e87916",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  );

  addLineLayer(
    map,
    "aeris-transmission-context",
    "aeris-transmission-context-source",
    {
      "line-color": "#7256b8",
      "line-width": 2,
      "line-opacity": 0.55,
    },
  );

  addLineLayer(
    map,
    "aeris-transmission-nearest",
    "aeris-transmission-nearest-source",
    {
      "line-color": "#8b3fd1",
      "line-width": 6,
      "line-opacity": 1,
    },
  );

  addLineLayer(
    map,
    "aeris-transmission-connector",
    "aeris-transmission-connector-source",
    {
      "line-color": "#8b3fd1",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  );

  addCircleLayer(
    map,
    "aeris-substation-context",
    "aeris-substation-context-source",
    {
      "circle-radius": 5,
      "circle-color": "#7256b8",
      "circle-opacity": 0.55,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
    },
  );

  addCircleLayer(
    map,
    "aeris-substation-nearest",
    "aeris-substation-nearest-source",
    {
      "circle-radius": 10,
      "circle-color": "#8b3fd1",
      "circle-opacity": 1,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 3,
    },
  );

  addLineLayer(
    map,
    "aeris-substation-connector",
    "aeris-substation-connector-source",
    {
      "line-color": "#8b3fd1",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  );

  addLineLayer(
    map,
    "aeris-stream-context",
    "aeris-stream-context-source",
    {
      "line-color": "#2a7fc1",
      "line-width": 2,
      "line-opacity": 0.55,
    },
  );

  addLineLayer(
    map,
    "aeris-stream-nearest",
    "aeris-stream-nearest-source",
    {
      "line-color": "#006bb6",
      "line-width": 5,
      "line-opacity": 1,
    },
  );

  addLineLayer(
    map,
    "aeris-stream-connector",
    "aeris-stream-connector-source",
    {
      "line-color": "#006bb6",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  );

  addFillLayer(
    map,
    "aeris-lake-context-fill",
    "aeris-lake-context-source",
    {
      "fill-color": "#4ca3dd",
      "fill-opacity": 0.22,
    },
  );

  addLineLayer(
    map,
    "aeris-lake-context-line",
    "aeris-lake-context-source",
    {
      "line-color": "#2a7fc1",
      "line-width": 1.5,
    },
  );

  addFillLayer(
    map,
    "aeris-lake-nearest-fill",
    "aeris-lake-nearest-source",
    {
      "fill-color": "#006bb6",
      "fill-opacity": 0.5,
    },
  );

  addLineLayer(
    map,
    "aeris-lake-nearest-line",
    "aeris-lake-nearest-source",
    {
      "line-color": "#004b80",
      "line-width": 4,
    },
  );

  addLineLayer(
    map,
    "aeris-lake-connector",
    "aeris-lake-connector-source",
    {
      "line-color": "#006bb6",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  );

  addFillLayer(
    map,
    "aeris-flood-fill",
    "aeris-flood-source",
    {
      "fill-color": "#d44b45",
      "fill-opacity": 0.2,
    },
  );

  addLineLayer(
    map,
    "aeris-flood-line",
    "aeris-flood-source",
    {
      "line-color": "#b42318",
      "line-width": 2,
      "line-opacity": 0.8,
    },
  );

  addFillLayer(
    map,
    "aeris-protected-fill",
    "aeris-protected-source",
    {
      "fill-color": "#208653",
      "fill-opacity": 0.22,
    },
  );

  addLineLayer(
    map,
    "aeris-protected-line",
    "aeris-protected-source",
    {
      "line-color": "#12633b",
      "line-width": 2,
      "line-opacity": 0.8,
    },
  );
}


function setSourceData(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection | undefined,
): void {
  const source = map.getSource(sourceId);

  if (
    source &&
    "setData" in source
  ) {
    (
      source as maplibregl.GeoJSONSource
    ).setData(data ?? EMPTY);
  }
}


export function updateEvidenceSources(
  map: maplibregl.Map,
  evidence: SiteMapEvidence | null,
): void {
  const layers = evidence?.layers;

  setSourceData(
    map,
    "aeris-road-context-source",
    layers?.road.nearby,
  );

  setSourceData(
    map,
    "aeris-road-nearest-source",
    layers?.road.nearest,
  );

  setSourceData(
    map,
    "aeris-road-connector-source",
    layers?.road.connector,
  );

  setSourceData(
    map,
    "aeris-transmission-context-source",
    layers?.transmission.nearby,
  );

  setSourceData(
    map,
    "aeris-transmission-nearest-source",
    layers?.transmission.nearest,
  );

  setSourceData(
    map,
    "aeris-transmission-connector-source",
    layers?.transmission.connector,
  );

  setSourceData(
    map,
    "aeris-substation-context-source",
    layers?.substation.nearby,
  );

  setSourceData(
    map,
    "aeris-substation-nearest-source",
    layers?.substation.nearest,
  );

  setSourceData(
    map,
    "aeris-substation-connector-source",
    layers?.substation.connector,
  );

  setSourceData(
    map,
    "aeris-stream-context-source",
    layers?.stream.nearby,
  );

  setSourceData(
    map,
    "aeris-stream-nearest-source",
    layers?.stream.nearest,
  );

  setSourceData(
    map,
    "aeris-stream-connector-source",
    layers?.stream.connector,
  );

  setSourceData(
    map,
    "aeris-lake-context-source",
    layers?.lake.nearby,
  );

  setSourceData(
    map,
    "aeris-lake-nearest-source",
    layers?.lake.nearest,
  );

  setSourceData(
    map,
    "aeris-lake-connector-source",
    layers?.lake.connector,
  );

  setSourceData(
    map,
    "aeris-flood-source",
    layers?.flood.nearby,
  );

  setSourceData(
    map,
    "aeris-protected-source",
    layers?.protected.nearby,
  );
}


export function applyEvidenceVisibility(
  map: maplibregl.Map,
  visibility: EvidenceVisibility,
): void {
  const groups: EvidenceGroup[] = [
    "roads",
    "grid",
    "water",
    "flood",
    "protected",
  ];

  groups.forEach((group) => {
    const mapVisibility =
      visibility[group]
        ? "visible"
        : "none";

    GROUP_LAYERS[group].forEach(
      (layerId) => {
        if (!map.getLayer(layerId)) {
          return;
        }

        map.setLayoutProperty(
          layerId,
          "visibility",
          mapVisibility,
        );
      },
    );
  });
}
