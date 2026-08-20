# AERIS API Guide

The FastAPI application exposes interactive OpenAPI documentation at:

```text
http://127.0.0.1:8000/docs
```

The generated contract is committed at `AERIS/backend/openapi.json`; frontend response types are generated from that document.

## Health

```text
GET /health
GET /analysis/statewide/health
GET /analysis/parcels/health
```

## Statewide screening

```text
GET /analysis/statewide/summary
GET /analysis/statewide/grid
GET /analysis/statewide/candidate-zones
GET /analysis/statewide/cells/{cell_id}
GET /analysis/statewide/zones/{zone_id}
GET /analysis/statewide/score-bands
GET /analysis/statewide/bias-audit
```

`/grid` supports score type/range, eligibility, equity gate, exclusion, county, and response-limit filters. Candidate zones support top/auto/exploration modes.

## Scoped parcel builds

Expensive GIS work is never triggered through GET. Start a build with:

```text
POST /analysis/parcels/build/zone/{zone_id}
POST /analysis/parcels/build/bbox
```

Both return a `202 Accepted` job record. Poll:

```text
GET /analysis/parcels/jobs/{job_id}
```

Terminal states are:

```text
completed
partial_failure
failed
```

A `partial_failure` preserves successful parcel/evidence artifacts and reports failed domains independently.

If `AERIS_BUILD_TOKEN` is configured on the backend, POST build calls must provide the matching `X-AERIS-Build-Token` header. A trusted reverse proxy or server-side API client should inject that secret; do not embed it in the browser bundle.

## Scoped parcel reads

```text
GET /analysis/parcels/scopes/{scope_id}/status
GET /analysis/parcels/scopes/{scope_id}/bundle
GET /analysis/parcels/scopes/{scope_id}/parcels/{parcel_id}
GET /analysis/parcels/scopes/{scope_id}/development-envelopes
GET /analysis/parcels/scopes/{scope_id}/largest-components
GET /analysis/parcels/scopes/{scope_id}/constraints
GET /analysis/parcels/scopes/{scope_id}/grid-evidence
GET /analysis/parcels/scopes/{scope_id}/planning-evidence
```

The bundle endpoint is the preferred browser read after a build. It returns parcel geometry plus every currently available domain and per-domain readiness/error status.

## Planning registry

```text
GET /analysis/parcels/planning/registry
```

This reports statewide 24-jurisdiction registry coverage and source-status counts. It does not imply that authoritative local zoning/permit adapters are configured.

## API semantics

- `409 scope_build_required` means the requested scoped artifact has not been built.
- Missing optional evidence does not invalidate successful evidence domains.
- Parcel detail returns `null` for an unbuilt optional domain.
- Capacity is never inferred from voltage/distance.
- Local zoning approval, permitted use, and entitlement clearance are never inferred from statewide planning context.
