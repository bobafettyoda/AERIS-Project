import assert from "node:assert/strict";
import test from "node:test";

import {
  applyParcelView,
  visibleLayersForView,
  VIEW_LAYERS,
} from "./viewLayers.ts";


test("every parcel view maps to an explicit non-empty layer group", () => {
  for (const [view, layers] of Object.entries(VIEW_LAYERS)) {
    assert.ok(layers.length > 0, `${view} has no configured layers`);
    assert.deepEqual(visibleLayersForView(view as keyof typeof VIEW_LAYERS), layers);
  }
});


test("applyParcelView hides every inactive group", () => {
  const visibility = new Map<string, string>();
  const knownLayers = new Set(Object.values(VIEW_LAYERS).flat());
  const fakeMap = {
    getLayer(layerId: string) {
      return knownLayers.has(layerId) ? { id: layerId } : undefined;
    },
    setLayoutProperty(layerId: string, property: string, value: string) {
      assert.equal(property, "visibility");
      visibility.set(layerId, value);
    },
  };

  applyParcelView(fakeMap as never, "constraints");

  for (const layerId of knownLayers) {
    assert.equal(
      visibility.get(layerId),
      VIEW_LAYERS.constraints.includes(layerId) ? "visible" : "none",
    );
  }
});
