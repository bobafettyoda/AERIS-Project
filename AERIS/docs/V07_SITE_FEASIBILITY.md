# AERIS v0.7 Physical Site Feasibility

## Purpose

AERIS v0.7 refines a parcel's v0.4 mapped-constraint envelope using
additional physical screening evidence:

- statewide LiDAR-derived elevation and slope;
- mapped wetlands and Wetlands of Special State Concern screening;
- statewide road-centerline proximity and frontage proxies;
- reference-only statewide building footprints;
- multi-parcel assemblage discovery;
- transparent parcel and assemblage comparison.

The result is called **preliminary physical site-feasibility evidence**.
It is not confirmed buildable land.

## Analysis sequence

```text
v0.4 development envelope
        ↓
subtract mapped wetlands
subtract configured steep-slope areas
        ↓
final preliminary site envelope
        ↓
measure largest contiguous component
measure road proximity/frontage proxy
measure reference building overlap
        ↓
classify parcel physical feasibility
        ↓
discover adjacent multi-parcel assemblages
```

## Terrain and slope

AERIS requests a scoped export from the Maryland statewide LiDAR DEM
mosaic and computes slope percent in the Maryland State Plane coordinate
system.

For each parcel analysis area, AERIS reports:

- elevation minimum, maximum, mean, and range;
- mean, median, and 90th-percentile slope;
- configured steep-slope overlap acreage and fraction;
- severe-slope pixel fraction for review.

The default screening thresholds are stored in
`configs/parcels/site_feasibility.yaml`. They are analytical assumptions,
not adopted grading standards.

AERIS does not confirm grading feasibility, earthwork quantities,
geotechnical conditions, drainage design, or survey accuracy.

## Wetlands

The configured statewide screening layers include:

- Maryland DNR wetlands polygons;
- National Wetlands Inventory polygons;
- Wetlands of Special State Concern.

Mapped wetlands are subtracted from the preliminary site envelope. The
configured Special State Concern buffer is a conservative screening
assumption.

AERIS does not confirm wetland boundaries, jurisdiction, permitting,
mitigation requirements, or field delineation.

## Road access and frontage

AERIS uses statewide interstate, U.S., Maryland, and local/other road
centerlines to report:

- nearest mapped road distance;
- nearest mapped road name and class;
- nearest primary-road distance;
- non-interstate road-frontage length proxy;
- limited-access road-adjacency proxy;
- nearest non-interstate road distance;
- final site-envelope-to-non-interstate-road distance;
- a descriptive road-access screening status.

Interstate adjacency is never treated as direct access. It receives a
separate `LIMITED_ACCESS_ROAD_ADJACENCY_REVIEW_REQUIRED` status unless a
mapped non-interstate access proxy is also present. Any road-centerline
overlap or proximity remains a screening proxy and does not prove legal
access, frontage ownership, curb-cut approval, driveway approval, safe
sight distance, or engineering feasibility.

## Existing-development reference

Maryland statewide building footprints are used only as a reference
screen. AERIS reports feature count, overlap acreage, and a coverage
fraction, and combines that evidence with parcel assessment/improvement
indicators to produce a relative redevelopment-burden class.

The building geometry is not treated as survey-grade and is not
subtracted from the site envelope in v0.7.

## Physical-feasibility classes

AERIS applies transparent thresholds from the versioned configuration:

- `STRONG_PRELIMINARY_SITE_FEASIBILITY`
- `PROMISING_PRELIMINARY_SITE_FEASIBILITY`
- `PHYSICAL_SITE_REVIEW_REQUIRED`
- `LIMITED_PHYSICAL_SITE_FEASIBILITY`

The class uses largest contiguous site acreage, mapped steep-slope and
wetland fractions, building-reference burden, and road-access status.
It remains independent of legal ownership, utility capacity, zoning
approval, and acquisition feasibility.

## Candidate score

The v0.7 candidate score is a transparent bounded screen using:

- largest contiguous site acreage;
- road-access status;
- slope fraction;
- wetland fraction;
- building-reference fraction.

The score is used only to organize preliminary physical candidates. It
is not an investment score, appraisal, or approval probability.

Before a parcel enters the comparison shortlist, AERIS applies separate
eligibility gates. Public/institutional parcels, parcels inheriting a
statewide hard exclusion, and parcels below the configured minimum
contiguous-area threshold remain visible as evidence but are not returned
as top comparison candidates.

## Multi-parcel assemblages

AERIS identifies spatially adjacent parcel site envelopes and groups them
with a configurable gap tolerance. Assemblages report:

- parcel count and parcel IDs;
- total preliminary site area;
- largest contiguous site area;
- component count;
- weighted slope, wetland, and building-reference fractions;
- best mapped road-access status;
- transparent candidate score.

An assemblage does not establish common ownership, parcel control,
acquisition feasibility, subdivision approval, or the ability to combine
parcels legally.

## Required safeguards

For every v0.7 result:

```text
legal_buildability_confirmed = false
wetland_delineation_confirmed = false
wetland_permitting_complete = false
road_access_confirmed = false
driveway_or_curb_cut_approved = false
terrain_engineering_complete = false
grading_plan_complete = false
building_geometry_survey_grade = false
parcel_assembly_control_confirmed = false
parcel_availability_confirmed = false
acquisition_feasibility_confirmed = false
```

## Outputs

Each scope produces:

- parcel site-analysis attributes;
- final preliminary site envelopes;
- largest site components;
- site constraint geometry;
- scoped road centerlines;
- reference building footprints in the audit GeoPackage;
- preliminary multi-parcel assemblages;
- top parcel/assemblage candidate records;
- a source/configuration/checksum manifest.
