import assert from "node:assert/strict";
import test from "node:test";

import type { ParcelDetail } from "../parcelApi.ts";
import { summarizeParcel } from "./summaryRules.ts";


function parcelFixture(overrides: Record<string, unknown> = {}): ParcelDetail {
  const base = {
    scope_id: "scope",
    parcel_id: "parcel",
    identity: {},
    parcel: {},
    source_development_indicators: {},
    classification: {
      public_land_flag: false,
      institutional_use_flag: false,
      existing_development_indicator: false,
      availability_status: "POTENTIAL_FURTHER_REVIEW",
      availability_reason: "Screening only",
      availability_confirmed: false,
      data_confidence: "HIGH",
    },
    statewide_context: {
      technical_score: 0.85,
      effective_score: 0.85,
      equity_gate: "PASS",
      hard_excluded: false,
      auto_eligible: true,
      exploration_eligible: true,
    },
    scope: {},
    source_dates: {},
    development_envelope: {
      preliminary_unconstrained_area_acres: 60,
      largest_contiguous_unconstrained_acres: 45,
      preliminary_envelope_only: true,
    },
    grid_feasibility: {
      public_grid_context_class: "STRONG_MAPPED_GRID_CONTEXT",
      nearest_transmission: {},
      transmission_within_5km: {},
      nearest_substation: {},
      substations_within_10km: {},
      capacity: {
        status: "UNKNOWN_NOT_IN_PUBLIC_SOURCE",
        available_capacity_mw: null,
        utility_confirmation_required: true,
        interconnection_study_required: true,
        electrical_service_feasibility_confirmed: false,
      },
      warning: "Capacity unknown",
    },
    planning_context: {
      jurisdiction: {},
      zoning: {
        local_verified: false,
        permitted_use_determined: false,
      },
      planning_sources: {},
      statewide_context: {
        critical_area_overlap: false,
      },
      decision: {
        planning_review_status: "LOCAL_ZONING_VERIFICATION_REQUIRED",
        data_confidence: "MEDIUM",
        manual_local_verification_required: true,
        active_development_clear: false,
        permit_clearance_determined: false,
        entitlement_clearance_determined: false,
      },
      warning: "Manual review",
    },
    warning: "Screening record",
  };

  return Object.assign(base, overrides) as unknown as ParcelDetail;
}


test("summary continues diligence for strong non-blocked evidence", () => {
  const summary = summarizeParcel(parcelFixture());
  assert.equal(summary.nextAction, "Continue preliminary diligence");
  assert.equal(summary.nextActionLevel, "positive");
  assert.ok(summary.strengths.includes("Strong regional technical suitability"));
  assert.ok(summary.unresolved.some((item) => item.includes("Utility capacity")));
});


test("summary blocks hard-excluded regional context", () => {
  const parcel = parcelFixture();
  parcel.statewide_context.hard_excluded = true;
  const summary = summarizeParcel(parcel);
  assert.equal(summary.sections[0]?.value, "HARD EXCLUDED");
  assert.equal(summary.nextActionLevel, "blocked");
});
