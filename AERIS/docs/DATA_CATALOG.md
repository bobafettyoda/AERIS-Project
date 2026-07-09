# AERIS Data Catalog

---

## Maryland Road Centerlines - Comprehensive

**Criterion**
- Road Access

**Purpose**
- Calculate nearest-road distance from a candidate site.
- Normalize road proximity into a 0–1 road access score.

**Source**
- Maryland iMAP
- MDOT SHA

**Access Method**
- ArcGIS REST Map Service

**REST Endpoint**
https://mdgeodata.md.gov/imap/rest/services/Transportation/MD_RoadCenterlinesComprehensive/MapServer/0

**Geometry**
- Polyline

**Study Area**
- Prince George's County
- Filter: `COUNTY = 16`

**Status**
- ✅ Connected
- ✅ County filter verified
- ✅ Count verified: 17,974 Prince George's County road features
- ✅ Paging implemented
- ✅ Distance analysis complete
- ✅ Normalization complete
- ✅ Weighted contribution connected to YAML decision model

**Current Normalization**
- Best: 800 m or closer
- Worst: 5000 m or farther
- Direction: closer is better

**Decision Model Weight**
- `road_access`: `0.0795`

---

## HIFLD Electric Power Transmission Lines

**Criterion**
- Grid Infrastructure

**Purpose**
- Calculate distance to nearest electric transmission line.
- Normalize transmission-line proximity into a 0–1 grid infrastructure score.

**Source**
- HIFLD / DOE public ArcGIS service

**Access Method**
- ArcGIS REST Feature Service

**REST Endpoint**
https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0

**Geometry**
- Polyline

**Study Area**
- United States
- To be filtered to Maryland / Prince George's County during analysis

**Status**
- ✅ Count verified: 74,553 features
- ✅ One-feature GeoJSON test verified
- 🔄 Distance analysis pending
- 🔄 Normalization pending
- 🔄 Weighted contribution pending

**Current Normalization**
- Planned: closer is better
- Preferred distance from decision model: `transmission_line_m = 4000`

**Decision Model Weight**
- `grid_infrastructure`: `0.154`