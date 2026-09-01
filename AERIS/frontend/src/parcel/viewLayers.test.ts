import assert from "node:assert/strict";
import test from "node:test";

import {
  VIEW_LAYERS,
  visibleLayersForView,
} from "./viewLayers.ts";


test("every parcel view has at least one map layer", () => {
  for (const [view, layers] of Object.entries(VIEW_LAYERS)) {
    assert.ok(
      layers.length > 0,
      `${view} should have map layers`,
    );
  }
});


test("site view contains site envelope and assemblage layers", () => {
  const layers = visibleLayersForView("site");

  assert.ok(
    layers.includes(
      "parcel-site-envelope-fill",
    ),
  );

  assert.ok(
    layers.includes(
      "parcel-site-assemblage-line",
    ),
  );
});


test("view layer groups are disjoint", () => {
  const all = Object.values(VIEW_LAYERS).flat();
  assert.equal(
    new Set(all).size,
    all.length,
  );
});
