# AERIS v0.5 Public Grid Feasibility Context

## Purpose

AERIS v0.5 adds parcel-level evidence about publicly mapped electric
transmission lines and substations.

It does not determine available electric capacity.

## Transmission evidence

For each parcel, AERIS reports:

- exact parcel-to-line distance;
- mapped line voltage;
- mapped voltage class;
- owner;
- status;
- endpoint substation names where available;
- inferred-data indicator;
- source and validation dates;
- number of mapped lines within five kilometers;
- maximum mapped voltage within five kilometers;
- mapped owners represented within five kilometers.

## Substation evidence

For each parcel, AERIS reports:

- exact parcel-to-substation distance;
- mapped substation name, type and status;
- maximum and minimum reported voltage;
- reported connected-line count;
- number of mapped substations within ten kilometers;
- maximum reported substation voltage within ten kilometers;
- source and validation dates.

## Public grid context classes

AERIS assigns a descriptive context class:

- `VERY_STRONG_MAPPED_GRID_CONTEXT`
- `STRONG_MAPPED_GRID_CONTEXT`
- `MODERATE_MAPPED_GRID_CONTEXT`
- `LIMITED_MAPPED_GRID_CONTEXT`
- `INSUFFICIENT_MAPPED_GRID_DATA`

These classes describe only the combination of mapped proximity and
reported voltage.

They are not service-capacity determinations.

## Capacity safeguards

For every parcel:

- `capacity_status = UNKNOWN_NOT_IN_PUBLIC_SOURCE`
- `available_capacity_mw = null`
- `utility_confirmation_required = true`
- `interconnection_study_required = true`
- `electrical_service_feasibility_confirmed = false`

A nearby high-voltage transmission line does not establish spare
transformer capacity, a feasible point of interconnection, available
utility service, acceptable system impacts, or an approved service
request.

## Source limitations

The public transmission and substation layers are screening datasets.
They may be incomplete, approximate, inferred, or older than current
utility conditions.

AERIS preserves source dates and confidence indicators so these
limitations remain visible.
