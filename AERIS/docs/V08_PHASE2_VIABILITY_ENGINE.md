# AERIS v0.8 Phase 2 — Viability Engine

## Purpose

Phase 2 changes AERIS from a fixed regional shortlist into an ordered siting workflow:

1. **Hard constraints first.** Regional cells intersecting configured hard exclusions are removed before weighted suitability is used.
2. **Regional search areas, not a fixed Top 5.** AERIS uses the coherent `auto` and `exploration` connected-component zones as search areas. The legacy Top-5 artifact remains only for backward compatibility with older releases.
3. **Parcel and usable-site evaluation.** A search area is built through the existing parcel, development-envelope, physical-site, grid-context, and planning-context pipelines.
4. **Configurable feasibility gates.** Land, environmental, road, mapped grid-context, and planning-evidence gates determine whether a site is rejected, placed on evidence hold, or allowed to advance.
5. **Explicit rejection reasons.** Every candidate receives machine-readable rejection, evidence-hold, and review reasons.
6. **Comparison only after viability screening.** The comparison endpoint accepts only candidates that passed the configured gates.

The engine is a screening and due-diligence prioritization tool. It does **not** claim that a candidate is development-ready, entitled, utility-capacity-confirmed, acquisition-controlled, or permit-approved.

## Research basis

The Phase 2 sequence follows the GIS-MCDA approach used in *GIS-Driven Regional Assessment for Sustainable Data Center Siting in the United Kingdom* (Hussain et al., 2026): constrained land is removed with binary exclusion before weighted suitability is used, coherent high-scoring areas are then identified for further comparison, and regional suitability is treated as a screen rather than proof of site-level development readiness.

The distinction between a high score and a robust/decision-ready result is also consistent with Ligmann-Zielinska and Jankowski (2014), which shows that high suitability can coexist with high uncertainty and should therefore trigger additional investigation rather than an unconditional recommendation.

AERIS does **not** copy the UK paper's site-specific thresholds into Maryland. The acreage, road, slope, wetland, and mapped-grid thresholds in `configs/viability/data_center_maryland.yaml` are explicit AERIS operational screening settings. They are configurable and are documented separately from literature-derived methodology.

## Configuration

Primary configuration:

```text
AERIS/configs/viability/data_center_maryland.yaml
```

Important defaults:

- Minimum regional suitability: **0.70**
- Minimum contiguous usable land: **25 acres**
- Minimum total preliminary site area: **25 acres**
- Maximum mapped wetland fraction: **10%**
- Maximum steep-slope fraction: **25%**
- Accepted mapped grid context: **moderate, strong, or very strong**
- Allowed mapped road screen: **direct frontage proxy or near mapped public road**

The contiguous-acreage, slope, wetland, and road defaults align with the existing AERIS `PROMISING_PRELIMINARY_SITE_FEASIBILITY` screen. The total-site acreage requirement remains a separate configurable viability safeguard.

## Status model

### `VIABLE_SCREENING_CANDIDATE`

Known screening gates pass. The candidate may advance to comparison. Review items such as utility capacity, interconnection, local entitlement, availability, wetland delineation, and acquisition control remain unresolved unless separately verified.

### `EVIDENCE_HOLD`

No known hard failure has been identified, but required screening evidence is missing or insufficient. The candidate cannot advance to comparison until the missing evidence is available.

### `REJECTED`

At least one configured screening gate fails, for example insufficient contiguous usable acreage, excessive mapped wetland/slope fraction, limited mapped grid context, road-access screen failure, public/institutional use, or inherited regional hard exclusion.

## API

### Methodology

```http
GET /analysis/viability/methodology
```

Returns the active viability configuration and safeguards.

### Search areas

```http
GET /analysis/viability/search-areas?mode=auto
```

Returns all qualifying regional search areas. It does not apply a fixed `top_n=5` selection.

Each search-area feature includes:

- `scope_id`
- `analysis_role=REGIONAL_SEARCH_AREA`
- `fixed_rank_shortlist=false`
- `viability_state`
- `comparison_eligible_count` when evaluation artifacts are ready

### Build/evaluate a search area

```http
POST /analysis/viability/search-areas/{zone_id}/evaluate
Content-Type: application/json

{"refresh": false}
```

This reuses the existing scoped build coordinator so parcel, envelope, site, grid, and planning evidence are generated once and remain compatible with Parcel Investigation.

### Scope viability

```http
GET /analysis/viability/scopes/{scope_id}
```

Returns:

- artifact readiness
- evaluated / eligible / hold / rejected counts
- rejection reason counts
- evidence-hold reason counts
- due-diligence review reason counts
- comparison-eligible candidates only
- safeguards and interpretation language

Use `?include_all=true` when audit/debug output for every evaluated parcel is required.

### Compare viable candidates

```http
POST /analysis/viability/scopes/{scope_id}/compare
Content-Type: application/json

{"candidate_ids": ["candidate-a", "candidate-b"]}
```

Candidates that did not pass viability screening are rejected by this endpoint even if they existed in an older physical-site candidate list.

## Viability score

A viability score is calculated **only after** a candidate passes the gates. It combines existing AERIS outputs rather than creating a second independent MCDA model:

```text
0.60 × physical-site candidate score
+ 0.40 × statewide technical suitability
```

If one component is unavailable, the available component is normalized over the remaining weight. Rejected and evidence-hold candidates receive no viability score.

The weights are operational ranking settings, not a claim that the literature establishes a universal 60/40 ratio.

## Frontend behavior

Phase 2 changes the existing experience in two important ways without attempting the full Phase 3 workspace redesign:

- Statewide Screening defaults to **Auto search areas** and no longer exposes a **Top 5** control.
- Parcel Investigation displays a Viability Engine summary and sends **only viability-screened candidates** into comparison.
- Site Evaluator keeps its five-slot local scratchpad, but the UI calls those records **exploratory points**. They are not official viability candidates and do not bypass the parcel/site gates.

The older physical-site candidate list remains in the site-feasibility manifest for traceability, but it is no longer the comparison authority.

## Compatibility

Phase 2 reuses existing Phase 1 persistent GIS data and generated parcel/site artifacts. A normal Phase 2 code release must not download the statewide GIS datasets again.

The legacy files below may remain in the data snapshot because older artifacts and rollback releases reference them:

```text
data/derived/maryland_candidate_zones_top5.geojson
```

Their presence does not mean Phase 2 uses a fixed Top-5 workflow.

## Acceptance criteria

Phase 2 is complete when:

- the frontend has no Top-5 regional-search control;
- `/analysis/viability/search-areas` returns the coherent regional search-area pool without fixed `top_n`;
- known hard failures are rejected before a viability score is assigned;
- missing core evidence produces an evidence hold rather than a false pass;
- every rejection/hold has an explicit reason;
- only candidates with `comparison_eligible=true` can use the viability comparison endpoint;
- backend tests pass;
- frontend tests/build/lint pass in the project environment;
- Phase 1 preflight/cutover/rollback behavior remains unchanged;
- no statewide GIS data is included in a normal code release.
