import type {
  Map as MapLibreMap,
} from "maplibre-gl";


export type ParcelView =
  | "parcels"
  | "envelopes"
  | "site"
  | "constraints"
  | "grid"
  | "planning";


export const VIEW_LAYERS:
Record<ParcelView, readonly string[]> = {
  parcels: [
    "parcel-fill",
    "parcel-line",
  ],
  envelopes: [
    "parcel-envelope-fill",
    "parcel-envelope-line",
  ],
  site: [
    "parcel-site-envelope-fill",
    "parcel-site-envelope-line",
    "parcel-site-largest-line",
    "parcel-site-constraint-fill",
    "parcel-site-road-line",
    "parcel-site-assemblage-fill",
    "parcel-site-assemblage-line",
  ],
  constraints: [
    "parcel-constraint-fill",
  ],
  grid: [
    "parcel-grid-transmission",
    "parcel-grid-substations",
  ],
  planning: [
    "parcel-planning-fill",
    "parcel-planning-line",
  ],
};


export function visibleLayersForView(
  view: ParcelView,
): readonly string[] {
  return VIEW_LAYERS[view];
}


export function applyParcelView(
  map: MapLibreMap,
  view: ParcelView,
): void {
  const visible = new Set(
    visibleLayersForView(view),
  );

  for (const layerIds of Object.values(
    VIEW_LAYERS,
  )) {
    for (const layerId of layerIds) {
      if (!map.getLayer(layerId)) {
        continue;
      }

      map.setLayoutProperty(
        layerId,
        "visibility",
        visible.has(layerId)
          ? "visible"
          : "none",
      );
    }
  }
}
