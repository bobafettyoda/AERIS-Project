# AERIS v0.6 Statewide Planning and Entitlement Context

## Coverage

AERIS represents all 23 Maryland counties and Baltimore City in a
statewide planning registry.

Every parcel is assigned:

- county jurisdiction;
- mapped municipality where applicable;
- planning-authority profile;
- planning-authority review status;
- statewide parcel zoning status;
- local zoning source status;
- comprehensive-plan source status;
- active-development source status;
- permit source status;
- planning review status;
- planning-data confidence.

## Statewide planning foundations

AERIS includes statewide context from:

- Maryland county boundaries;
- Maryland municipal boundaries;
- Priority Funding Areas;
- Critical Areas;
- Enterprise Zones;
- Sustainable Communities;
- Foreign Trade Zones;
- RISE Zones;
- Opportunity Zones.

These overlays provide screening context. They do not determine project
approval.

## Zoning

The parcel record may contain a statewide zoning attribute.

That field is not treated as a current, authoritative local zoning
determination.

Unless a configured local adapter verifies zoning:

- `local_zoning_verified = false`
- `permitted_use_determined = false`
- `manual_local_verification_required = true`

## Active development and permits

When a jurisdiction has no configured automated source, AERIS reports
that status explicitly.

It does not interpret unavailable automation as:

- no active application;
- no approved development plan;
- no permit;
- no entitlement conflict.

## Local adapters

The v0.6 architecture supports jurisdiction-specific adapters.

Adapters may later retrieve:

- authoritative local zoning geometry;
- comprehensive or master-plan designations;
- overlay districts;
- active site plans;
- subdivision applications;
- development approvals;
- permit evidence.

A local adapter must preserve source, date, method, confidence, and
warning information.

## Safeguards

AERIS does not infer:

- zoning approval;
- permitted use;
- absence of active development;
- absence of permits;
- entitlement clearance.

Planning evidence remains a diligence input, not a legal determination.
