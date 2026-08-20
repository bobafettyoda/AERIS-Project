# AERIS Analysis Methods

## Decision architecture

AERIS separates four concepts that must not be collapsed into one score:

1. **Regional technical suitability** — weighted eight-criterion screening at 1 km resolution.
2. **Hard exclusions and effective suitability** — mapped constraints that can reduce effective suitability to zero without erasing the underlying technical score.
3. **Parcel physical feasibility** — real parcel geometry, candidate-zone overlap, mapped constraints, and contiguous preliminary land area.
4. **Diligence risk** — grid uncertainty, zoning/planning source coverage, ownership/availability, permitting, utility capacity, and other unresolved reviews.

Equity and community-impact evidence remain separate from the technical score. They may affect screening gates and audit outcomes but never increase technical suitability.

## Statewide grid

AERIS creates a one-kilometer grid in Maryland State Plane (`EPSG:26985`), clips it to the configured Maryland land mask, removes cells below the configured land fraction, and stores representative analysis points. Stable cell IDs support joins across every statewide pipeline.

## Eight technical criteria

Each criterion is normalized to a 0–1 score using its configured distance curve, band, or binary suitability rule. A final technical score is calculated only when every required criterion is complete. Configured criterion weights are normalized before aggregation.

The current criteria are:

- climate;
- grid infrastructure;
- telecommunications;
- protected areas;
- surface water;
- population density;
- road access;
- hydro hazard.

## Hard exclusions

Mapped surface-water, protected-land, and configured flood/SFHA conditions are tracked explicitly. A hard-excluded cell preserves its technical score for context but receives an effective suitability of zero and cannot become auto-screen eligible.

## Equity gate and bias audit

EnviroScreen attributes are joined at tract level. Official community flags are preferred; documented fallback thresholds are used only when the cached source lacks those Boolean fields. The equity gate is not part of the weighted technical score.

Candidate-zone outputs are audited for disparate outcomes, geographic concentration, and technical-weight sensitivity. A flagged audit does not erase the analytical result; it changes release and interpretation status to review required.

## Candidate zones

Eligible cells are grouped using rook adjacency so diagonal contact alone does not merge zones. Zone summaries include cell count, area, score statistics, county composition, equity composition, and exclusion evidence. Top zones are selected with configured spatial separation to avoid returning several parts of the same local cluster.

## Scoped parcel acquisition

Parcel acquisition is deliberately bounded by candidate zone or WGS84 bounding box. The ArcGIS source is queried by ObjectID in adaptive pages, cached, fingerprinted by source/config/scope, normalized, repaired if needed, and written atomically.

The full parcel polygon is preserved. `scope_overlap_area_acres` and `scope_overlap_fraction` describe only the portion intersecting the selected analysis scope.

Parcel availability is never confirmed. Public/institutional and existing-use classifications are conservative screening flags with explicit rule evidence.

## Statewide context linkage

A parcel is linked first to the AERIS grid cell with the greatest polygon overlap. A nearest representative-point join is used only as a fallback. County, regional score, exclusion, equity, and eligibility context are inherited from that linked cell.

## Preliminary mapped-constraint envelope

Within the parcel/scope intersection, AERIS unions configured subtractive constraints, calculates unique constrained acreage, subtracts that union, and reports:

- total analysis acreage;
- source-specific raw overlap;
- unique mapped constrained acreage;
- preliminary unconstrained acreage and fraction;
- largest contiguous unconstrained component;
- component count.

Review-only layers such as the FAA notice-distance screen are measured but not subtracted.

## Public grid context

Exact planar distance is measured from full parcel geometry to mapped transmission and substation geometry. The nearest feature is retained, along with nearby counts and maximum mapped voltage within configured radii. Descriptive grid-context classes are rule-based public-map summaries only.

Available capacity is always unknown unless a future utility-authoritative source explicitly supplies it.

## Planning context

Every parcel is assigned county context and representative municipal context, with overlap acreage/fraction retained for boundary-straddling parcels. Priority Funding Area and other statewide planning overlays are intersected locally.

The 24-jurisdiction registry exposes local source coverage states. Generic municipal boundaries do not automatically establish municipal zoning authority; county and municipal authority remains verification-required unless an authoritative matrix or local adapter resolves it.

## Build and publication model

Expensive scoped processing uses explicit POST build jobs. Builds are protected with per-scope locks, output GeoPackages are written to temporary paths and atomically published, and optional evidence domains may fail independently. GET routes only read completed artifacts.

## Confidence and interpretation

AERIS uses descriptive confidence/status fields rather than hiding missing evidence. The application must distinguish:

- source unavailable;
- source configured but unmatched;
- derived proxy;
- authoritative local evidence;
- manual verification required.

No AERIS output by itself confirms parcel availability, buildability, utility capacity, permitted use, entitlement clearance, or project approval.
