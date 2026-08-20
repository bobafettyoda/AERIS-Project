# AERIS User Guide

## The three questions AERIS answers

### 1. Where should we look?

The statewide model compares 1 km screening cells across Maryland using technical criteria, exclusions, and separate equity evidence. It identifies candidate zones for further investigation.

### 2. What real land is there?

Parcel Investigation retrieves real parcel polygons inside a selected candidate zone. It preserves the full parcel geometry, reports the parcel portion inside the zone, and surfaces statewide property attributes without claiming vacancy or availability.

### 3. What could make development difficult?

AERIS adds separate evidence domains:

- **Envelopes** — preliminary land remaining after configured mapped constraints;
- **Constraints** — water, protected land, SFHA screening, runway pavement, and FAA notice context;
- **Grid** — mapped line/substation distance and voltage, with capacity explicitly unknown;
- **Planning** — jurisdiction, statewide zoning field, planning overlays, and local-source coverage status.

## Map modes

| Mode | Meaning | It does not prove |
|---|---|---|
| Parcels | Legal/tax-map screening polygons and source attributes | ownership availability or vacancy |
| Envelopes | Preliminary mapped-constraint land inside the analysis scope | legal buildability |
| Constraints | The mapped geometries used for physical screening | a complete permitting determination |
| Grid | Publicly mapped transmission and substation context | available MW or interconnection approval |
| Planning | Statewide jurisdiction and planning context | permitted use or zoning approval |

## Key geography terms

- **Grid cell:** AERIS’s 1 km statewide analytical unit.
- **Candidate zone:** A contiguous group of promising grid cells.
- **Census tract:** Demographic and equity geography.
- **Parcel:** A property/tax-map polygon.
- **Development envelope:** The parcel portion remaining after configured mapped constraints.

## Status interpretation

### `STATEWIDE_BASELINE_ONLY`

A statewide parcel field is available, but an authoritative local zoning adapter has not verified it.

### `SOURCE_DISCOVERY_REQUIRED`

AERIS does not yet have a configured automated source. This never means the record or restriction does not exist.

### `UNKNOWN_NOT_IN_PUBLIC_SOURCE`

The requested conclusion—such as available utility capacity—is not supported by the public source.

### `PUBLIC_OR_INSTITUTIONAL`

Parcel source attributes indicate a public or institutional use. It is a conservative review flag, not a legal ownership determination.

## Recommended analyst workflow

1. Use Statewide Explorer to identify a candidate zone.
2. Open Parcel Investigation and build the scoped evidence bundle.
3. Read the preliminary screening summary before opening detailed evidence.
4. Reject or pause on obvious hard exclusions, public/institutional conflicts, or negligible contiguous land.
5. Review grid evidence without inferring capacity.
6. Review planning evidence and identify which local sources remain manual.
7. Produce a diligence question list before spending money on detailed studies.

## What AERIS can responsibly say today

> This region is technically promising. These parcels intersect the candidate zone. This amount of land remains after the configured mapped constraints. Public grid infrastructure is mapped nearby. These planning and jurisdictional facts are known, and these specific questions remain unresolved.

## What AERIS cannot responsibly say today

- the parcel is for sale;
- the parcel is vacant;
- the land is legally buildable;
- a data center is permitted by right;
- the utility can serve a requested load;
- an interconnection is approved;
- permits or active plans do not exist merely because automation is unavailable.

# Comprehension quiz

1. A statewide cell scores 0.91 but is hard-excluded. Which score should guide eligibility?
2. A 200-acre parcel overlaps a candidate zone by 20 acres. Which acreage does the envelope analyze?
3. A parcel has 70 unconstrained acres but a 12-acre largest contiguous component. Which number is more relevant to a large campus?
4. A 500 kV line crosses the parcel. What can AERIS conclude about available capacity?
5. What does `STATEWIDE_BASELINE_ONLY` mean for zoning?
6. Does `SOURCE_DISCOVERY_REQUIRED` for permits mean no permits exist?
7. Explain the difference between a candidate zone, parcel, and development envelope.
8. Why can a high technical score still lead to a poor parcel candidate?

## Answer key

1. The effective/exclusion outcome; a hard-excluded cell is not eligible regardless of technical score.
2. The 20-acre portion inside the configured analysis scope.
3. The largest contiguous component, because fragmented acreage may not fit a large facility.
4. Only that high-voltage infrastructure is publicly mapped nearby; capacity remains unknown.
5. A statewide field exists, but current authoritative local zoning remains unverified.
6. No. It means AERIS lacks an automated source and manual verification is required.
7. The zone is a regional cluster of cells; the parcel is the property polygon; the envelope is mapped land remaining within the analyzed parcel portion.
8. The parcel may be excluded, occupied, public/institutional, too small, fragmented, capacity-constrained, or subject to unresolved planning issues.
