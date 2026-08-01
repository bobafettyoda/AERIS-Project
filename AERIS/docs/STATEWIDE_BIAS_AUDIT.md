# AERIS Statewide Bias and Concentration Audit

## Purpose

The audit checks whether AERIS statewide screening outcomes are
disproportionately concentrated in communities with elevated
environmental-justice, pollution, socioeconomic, racial/ethnic, or
language indicators.

Demographic attributes never increase technical suitability.

## Reference cohort

The reference cohort contains Maryland grid cells that:

- have all eight technical criteria;
- meet the regional land-fraction threshold;
- are not hard excluded.

## Selected cohort

The primary selected cohort contains cells inside the spatially
separated top-five baseline auto-screen candidate zones.

A second audit examines the complete baseline auto-screen candidate
pool.

## Indicators

The audit evaluates:

- environmental-justice percentile;
- pollution-burden percentile;
- environmental-effects percentile;
- sensitive-populations percentile;
- minority or Hispanic population percentage;
- low-income population percentage;
- limited-English population percentage.

## Measures

For each indicator, AERIS reports:

- area-weighted mean in the reference cohort;
- area-weighted mean in the selected cohort;
- share at or above the configured threshold;
- representation ratio;
- percentage-point difference;
- standardized mean difference;
- missing-data share.

## Concentration review

AERIS compares county shares in the selected cohort with county shares
in the technically eligible reference area.

A separate sensitivity audit increases each technical criterion weight
one at a time and checks whether geographically separated top results
remain concentrated in the same counties.

## Audit outcomes

### PASS

No configured material-disparity or concentration threshold was
triggered, and selected-cell data are sufficiently complete.

### FLAGGED

At least one configured disparity or concentration threshold was
triggered. Automatic shortlist release is blocked pending review.

### INSUFFICIENT_DATA

The selected cohort is too small or required audit fields are missing.
Automatic shortlist release is blocked.

## Limits

This is a spatial disparate-outcome screen. It is not a causal analysis,
population-exposure model, civil-rights determination, or substitute for
community engagement.

A passing audit does not make a zone buildable. Parcel, zoning,
wetlands, sensitive receptors, utility capacity, ownership, engineering,
permitting, public-health, and community reviews remain required.
