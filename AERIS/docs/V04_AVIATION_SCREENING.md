# AERIS v0.4 Aviation Screening

## Source

AERIS uses the FAA 28 Day NASR Airports and Other Landing Facilities CSV
subscription.

The configured v0.4 snapshot is effective August 6, 2026.

## Physical runway hard conflict

AERIS constructs physical runway-pavement polygons from:

- FAA physical runway-end coordinates;
- FAA reported runway width.

Only the physical runway polygon is subtracted from the preliminary
development envelope.

AERIS does not infer an airport-property boundary from the airport
reference point or reported airport acreage.

## Part 77 notice-distance screening

AERIS constructs a non-subtractive review overlay using the horizontal
distances in 14 CFR 77.9:

- 20,000 feet for airports whose longest runway exceeds 3,200 feet;
- 10,000 feet for airports whose longest runway does not exceed
  3,200 feet;
- 5,000 feet for configured heliport records.

These polygons represent only the horizontal notice-screening extent.

They do not evaluate:

- proposed structure height;
- the applicable upward slope at the proposed location;
- shielding;
- terrain;
- airport eligibility under every subsection of 14 CFR 77.9;
- an FAA aeronautical study;
- an FAA determination.

A parcel overlapping this layer is marked for height-dependent FAA
pre-screening. It is not automatically excluded.

## Not included

The current v0.4 aviation implementation does not claim to include:

- airport property boundaries;
- runway protection zones;
- runway safety areas;
- object-free areas;
- obstacle-free zones;
- approach surfaces;
- FAA approval.

Those require authoritative airport GIS or project-specific review.
