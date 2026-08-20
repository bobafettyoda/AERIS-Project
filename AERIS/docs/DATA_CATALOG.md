# AERIS Data Catalog

This catalog describes the datasets currently wired into the AERIS v0.6.1 screening workflow. Runtime manifests record the exact feature counts, checksums, source fields, and snapshot dates used by each build.

## Source-quality vocabulary

- **Authoritative baseline** — statewide or federal source used directly for screening.
- **Authoritative local adapter** — local jurisdiction source verified and normalized by a configured adapter.
- **Screening reference** — useful public geometry that may be incomplete, approximate, or dated.
- **Derived** — AERIS output calculated from one or more source layers.
- **Unavailable/manual review** — a category AERIS does not currently automate; absence is never interpreted as no restriction.

## Statewide analytical foundation

| Dataset | Provider | Role | Coverage/status |
|---|---|---|---|
| Maryland political/physical boundaries | Maryland iMAP | Land mask, counties, municipalities, statewide study area | Authoritative baseline |
| TIGER/Line census tracts | U.S. Census Bureau | Tract geometry and ACS linkage | Authoritative baseline; cached snapshot |
| ACS tract population | U.S. Census Bureau | Population density criterion | Authoritative baseline; cached snapshot |
| Maryland EnviroScreen | Maryland Department of the Environment / iMAP | Equity and disparate-outcome evidence; never increases technical score | Authoritative baseline with explicit fallback classification and missing-data status |
| Maryland 1 km land grid | AERIS derived | Common statewide analytical unit | 27,596 retained land cells |

## Technical suitability inputs

| Criterion | Primary source | Main evidence | Notes |
|---|---|---|---|
| Climate | NASA POWER regional data | Annual and July mean temperature | Cached statewide climate snapshot; source-distance evidence retained |
| Grid infrastructure | HIFLD transmission lines and electric substations | Exact/nearest distance, mapped voltage, owner/status, substation context | Screening reference; available capacity is never inferred |
| Telecommunications | Maryland broadband service-area data | Fiber/service proximity and provider diversity | Public mapped context, not a service commitment |
| Protected areas | Maryland Protected Lands service | Direct protected-land intersection/distance | Hard-exclusion evidence where configured |
| Surface water | Maryland detailed rivers/streams and lakes | Water intersection/distance | Direct mapped constraint |
| Population density | Census TIGER/ACS | People per square kilometer | Technical score independent of demographic equity attributes |
| Road access | Maryland interstate/U.S./Maryland route layers | Major-road proximity | Proximity does not prove legal or engineering access |
| Hydro hazard | Maryland-hosted Effective FEMA Floodplain | SFHA intersection/distance plus AERIS 91 m screening buffer | The 91 m buffer is a screening assumption, not a legal setback |

## Parcel backbone

| Dataset | Provider | Role | Notes |
|---|---|---|---|
| Maryland Parcel Boundaries | Maryland iMAP / Maryland Department of Planning / SDAT | Statewide legal/tax-map parcel geometry and baseline attributes | Queried only for a candidate zone or bounding box; not survey-grade and does not confirm availability |
| Parcel property attributes embedded in statewide layer | Maryland Planning / SDAT | Address, acreage, statewide zoning field, land-use/exemption/improvement indicators and source dates | Missing fields remain unavailable; no vacancy claim |
| Statewide final AERIS grid | AERIS derived | Regional score, exclusion, equity, and eligibility inherited by parcel | Linked using maximum grid overlap with nearest fallback |

## Preliminary development-envelope inputs

| Dataset | Role in envelope | Subtractive? |
|---|---|---:|
| Maryland surface water snapshot | Physical mapped constraint | Yes |
| Maryland protected lands snapshot | Protected-property constraint | Yes |
| Effective FEMA SFHA plus configured AERIS buffer | Flood screening constraint | Yes |
| FAA physical runway pavement derived from NASR runway endpoints and width | Physical runway conflict | Yes |
| FAA Part 77 notice-distance screen | Height-dependent aviation review context | No |

The output is a **preliminary mapped-constraint envelope**, not confirmed buildable land. Wetlands, terrain, buildings, local setbacks, rights-of-way, utilities, title, and engineering are not yet fully modeled.

## FAA aviation

| Source | Provider | Role | Snapshot |
|---|---|---|---|
| 28 Day NASR Airports and Other Landing Facilities CSV | Federal Aviation Administration | Airport points, runway centerlines, physical runway pavement, Part 77 notice-distance screening | Cataloged in `configs/application.json` and the aviation manifest |

AERIS does not infer airport property boundaries, runway protection zones, proposed-height compliance, or FAA approval.

## Public grid context

| Source | Provider | Fields used |
|---|---|---|
| U.S. Electric Power Transmission Lines | HIFLD public ArcGIS service | Voltage, voltage class, owner, status, source/validation date, endpoint substations |
| Electric Substations | HIFLD public ArcGIS service | Maximum/minimum voltage, line count, type, status, source/validation date |

AERIS reports exact parcel-to-geometry distance and nearby feature summaries. It always records:

```text
capacity_status = UNKNOWN_NOT_IN_PUBLIC_SOURCE
utility_confirmation_required = true
interconnection_study_required = true
```

## Statewide planning context

| Dataset | Provider | Role |
|---|---|---|
| County and municipal boundaries | Maryland iMAP | Jurisdiction and municipal overlap evidence |
| Priority Funding Areas | Maryland Planning / iMAP | Statewide planning context |
| Critical Areas | Maryland iMAP | Critical Area overlap acreage and context |
| Enterprise Zones | Maryland business/economy GIS | Incentive/planning context |
| Sustainable Communities | Maryland business/economy GIS | Incentive/planning context |
| Foreign Trade Zones | Maryland business/economy GIS | Incentive/planning context |
| RISE Zones | Maryland business/economy GIS | Incentive/planning context |
| Opportunity Zones | Maryland business/economy GIS | Incentive/planning context |

The registry represents all 23 counties plus Baltimore City. Unless a local adapter is explicitly configured, local zoning, comprehensive plans, active development, and permits remain `STATEWIDE_BASELINE_ONLY`, `MANUAL_REVIEW_REQUIRED`, or `SOURCE_DISCOVERY_REQUIRED`.

## Derived products

- statewide foundation, infrastructure, access, environmental, climate/final GeoPackages;
- statewide heatmap preview;
- candidate-zone, membership, sensitivity, score-band, and bias-audit outputs;
- scoped normalized parcel GeoPackages;
- preliminary parcel-envelope GeoPackages;
- FAA aviation screening GeoPackage;
- parcel public-grid context GeoPackages;
- parcel planning-context GeoPackages;
- manifests with checksums, counts, source fields, safeguards, and methodology.

Large source and derived GIS artifacts are intentionally ignored by Git. They must be generated through the scripts in `AERIS/backend/scripts` and validated with the matching review commands.
