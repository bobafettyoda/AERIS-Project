# AERIS v0.6.1 Stabilization

v0.6.1 is an engineering and product-clarity milestone rather than a new analytical criterion.

## Reliability

- expensive scope builds moved to explicit POST jobs;
- GET artifact routes are read-only;
- per-scope interprocess locks prevent duplicate builds;
- GeoPackages are written to temporary files and atomically published;
- optional evidence domains fail independently;
- build progress and artifact status are persisted under ignored runtime data.

## Performance

- parcel detail reads use indexed single-row GeoPackage queries;
- `parcel_id` indexes are created on derived parcel-analysis layers;
- browser grid payloads omit thousands of parcel connector geometries;
- a single scope bundle retrieves current map artifacts after a build.

## Architecture

- shared I/O, geometry, locking, GeoPackage, progress, statistics, and ArcGIS utilities are separated from domain pipelines;
- API contracts use Pydantic response models;
- frontend contract types are generated from the FastAPI OpenAPI document;
- parcel map view visibility is declarative;
- parcel scope build/load state is isolated in a React hook;
- control and screening-summary components are separated from the map shell.

## Product clarity

- parcel detail begins with a transparent preliminary screening summary;
- strengths, unresolved questions, and next action are displayed before raw evidence;
- evidence-domain readiness is visible;
- unavailable evidence does not erase successful domains.

## Additional hardening completed

- statewide API caches now invalidate automatically when source files change;
- raw parcel snapshots and page caches are fingerprinted by source, fields, scope, and ObjectID batch;
- bulk parcel-to-grid connector geometry is no longer generated;
- municipality and Priority Funding Area assignment now includes overlap acreage/fraction evidence;
- generic municipal-boundary matches no longer overstate municipal zoning authority;
- GeoJSON API services avoid serialize-then-parse memory duplication;
- application release and snapshot labels are generated from one versioned catalog;
- parcel details are split into regional, physical, grid, planning, and source-evidence components;
- frontend unit tests cover map-layer switching and summary rules;
- stale zone requests cannot overwrite a newer selected scope;
- statewide and parcel response contracts are generated from Pydantic/OpenAPI models;
- data catalog and analysis-method documentation reflect the current statewide system.
