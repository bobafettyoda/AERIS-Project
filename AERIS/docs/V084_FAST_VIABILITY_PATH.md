# AERIS v0.8.4 — Fast Viability Path

## Purpose

AERIS v0.8.4 keeps the Phase 2 Viability Engine authoritative while reducing the amount of expensive GIS work performed during search-area investigation.

The key rule is:

> If an inexpensive, already-authoritative gate proves that a parcel cannot advance, later evidence is not allowed to reverse that rejection and is therefore not required merely to rediscover the same final status.

This release is a performance change, not a threshold change. The Phase 2 `advance / evidence hold / reject` semantics and comparison-eligibility rules remain authoritative.

## Fast-path sequence

The search-area workflow becomes:

```text
Parcel acquisition
        ↓
Preliminary development envelope (existing v0.4 evidence)
        ↓
AUTHORITATIVE FAST GATES
  public / institutional use
  statewide hard exclusion
  total preliminary envelope < Phase 2 minimum
  largest contiguous preliminary envelope < Phase 2 minimum
        ↓
Preserve parcels that could participate in a viable assemblage
        ↓
DETAILED SITE ANALYSIS — survivors only
  wetlands
  terrain / slope
  final site envelope
  road-access metrics
  building-reference metrics
  candidate classification
  assemblages
        ↓
PRE-INFRASTRUCTURE VIABILITY GATES
        ↓
Grid + planning only when at least one candidate can still advance
        ↓
Authoritative Viability Engine
```

## Why the preliminary envelope is safe as an upper-bound gate

The existing development-envelope layer already subtracts the mapped v0.4 hard physical constraints and records:

- preliminary unconstrained area;
- largest contiguous unconstrained area;
- mapped constraint overlap.

The later physical-site pipeline subtracts additional wetland and configured steep-slope geometry. Those operations can only keep or reduce usable acreage; they cannot create more usable acreage.

Therefore, if the preliminary envelope is already below either Phase 2 requirement:

- `minimum_total_site_acres = 25.0`, or
- `minimum_contiguous_usable_acres = 25.0`,

then later site analysis cannot reverse that rejection. AERIS records the exact Phase 2 reason code and skips detailed site evidence for that individual parcel.

The preliminary development envelope itself is intentionally retained. It is the inexpensive upper-bound evidence that makes the short-circuit provable.

## Assemblage safeguard

A parcel that is too small individually is **not automatically discarded** when it could contribute to a multi-parcel assemblage.

Before skipping detailed analysis, AERIS performs a conservative adjacency upper-bound screen using the preliminary development-envelope geometry. A connected group is preserved for detailed analysis when:

- parcels meet the configured minimum parcel contribution;
- the group has at least the configured minimum parcel count;
- public/institutional/hard-excluded parcels are excluded from the potential group; and
- the sum of preliminary envelope acreage can still meet the Phase 2 total-site threshold.

Because this uses preliminary envelope acreage as an upper bound, it errs toward doing extra detailed work rather than prematurely eliminating a potentially viable assemblage.

## Downstream Grid and Planning behavior

After detailed physical-site analysis, AERIS evaluates the Phase 2 gates that can definitively reject a candidate before Grid or Planning evidence is considered.

If **no candidate in the scope can still advance**, AERIS does not run the scope-wide Grid or Planning builders. Their job artifacts are reported as logically complete with:

```text
NOT_REQUIRED_AFTER_AUTHORITATIVE_REJECTION
```

and the Viability Engine evaluates the already-definitive rejection records.

If one or more candidates survive the pre-infrastructure gates, the existing Grid and Planning pipelines still run unchanged for the scope. v0.8.4 does not introduce a new partial-scope Grid/Planning storage format; this avoids changing evidence semantics or risking omissions for surviving candidates.

## Progress and timing instrumentation

The physical-site pipeline now reports work-oriented stages instead of a single long `site_metrics` plateau. Examples include:

```text
fast_gate_4058_skipped_2_detailed
site_envelopes_1_of_2
site_metrics:roads_nearest_1_of_2
site_metrics:buildings_spatial_join
site_metrics:classification
assemblages
writing_outputs
```

The site manifest records:

```json
{
  "fast_path": {
    "parcel_count": 4060,
    "fast_rejected_count": 4058,
    "detailed_analysis_count": 2,
    "downstream_evidence_required_count": 0
  },
  "stage_timings_seconds": {},
  "performance_comparison": {}
}
```

Actual counts above are illustrative until AUTO-Z002 is rebuilt under v0.8.4.

The build-job record also stores artifact-level `timings_seconds` for parcel, envelope, site, grid, and planning stages.

## AUTO-Z002 benchmark path

The v0.8.3 AUTO-Z002 run persisted a site-feasibility manifest in shared GIS data. The first v0.8.4 rebuild reads that previous manifest before replacement and records:

- previous pipeline version;
- previous elapsed seconds;
- previous detailed-analysis count;
- current elapsed seconds;
- current detailed-analysis count;
- measured speedup when the previous run was from a different pipeline version.

After the v0.8.4 production analysis finishes, report it with:

```bash
cd ~/projects/AERIS-Project/AERIS/backend
PYTHONPATH=. python scripts/benchmark_fast_viability.py --scope-id zone-auto-z002
```

This is the production benchmark. No production speedup is claimed until that run is measured.

## Decision invariants

The optimized path must preserve these Phase 2 rules:

- `REJECTED` always wins when a configured rejection gate fails;
- `EVIDENCE_HOLD` is used only when no rejection exists and required evidence is unresolved;
- `VIABLE_SCREENING_CANDIDATE` is used only when no rejection/hold remains;
- only `comparison_eligible=true` candidates may enter comparison;
- utility capacity remains unconfirmed unless actually confirmed;
- an interconnection study remains required when configured;
- local planning verification remains required when configured;
- public mapped grid context does not establish available utility capacity.

For fast-rejected records, AERIS carries the exact authoritative Phase 2 rejection reason into the Viability Engine and does not fabricate hold/review reasons for evidence that was intentionally not calculated after the rejection became terminal.

## Phase 2 threshold preservation

v0.8.4 does **not** modify `AERIS/configs/viability/data_center_maryland.yaml`.

The installer verifies that file's checksum is identical before and after installation.

It also does not modify:

- statewide AHP/WLC weights;
- hard-constraint definitions;
- Dockerfiles or Compose;
- GeoNode Nginx routes;
- release install/rollback scripts;
- persistent GIS data;
- frontend npm dependencies.

## Regression coverage

The release adds tests for:

1. authoritative acreage upper-bound rejection;
2. public-land early rejection;
3. assemblage preservation for connected small parcels;
4. a 4,060-parcel synthetic scope where 4,058 obviously undersized isolated parcels are removed from detailed site analysis while two larger parcels continue;
5. identical final `REJECTED` / comparison-ineligible semantics between full evidence and fast rejection;
6. downstream-evidence filtering after pre-infrastructure gates;
7. Phase 2 configuration flags remaining authoritative;
8. mixed fast-path and viable records retaining correct scope counts;
9. Grid/Planning short-circuit only when no downstream candidate remains;
10. Grid/Planning readiness remaining required when survivors exist.

## Release identity

- application version: `0.8.4`
- release label: `v0.8.4`
- release stage: `fast-viability-path`
- physical-site pipeline version: `0.8.4`
