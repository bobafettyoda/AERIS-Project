# AERIS Maryland Statewide Analysis

## Purpose

AERIS v0.2 expands the point-based Maryland screening tool into a
statewide regional suitability surface.

The statewide product is a screening system. It does not identify
immediately buildable parcels or replace utility, zoning, engineering,
environmental, permitting, or community review.

## Coarse-to-fine workflow

### Stage 1: statewide 1 km screening

Maryland is divided into approximately 1 km analysis cells. Each cell
uses a representative point inside the Maryland boundary.

The statewide table will store:

- all eight normalized technical-criterion scores;
- technical hard exclusions;
- data-completeness status;
- MDEnviroScreen equity-gate status;
- source and model versions;
- final technical suitability under the baseline model.

### Stage 2: scenario analysis

Technical weights may be adjusted for a custom scenario.

Weights are automatically normalized to total 1.0.

Demographic attributes are never used to increase technical
suitability.

Hard exclusions and the equity gate remain separate from the
technical weighted score.

### Stage 3: candidate discovery

Users may:

- show technical suitability as a heat map;
- filter cells by score band;
- search for opportunities between 70 and 90;
- select the top 3 or top 5 technically suitable zones;
- require minimum geographic spacing between suggested zones;
- filter by county or other approved geography.

High-burden and insufficient-data areas cannot be automatically
recommended.

Caution areas may appear in exploratory searches only with a visible
enhanced-review warning.

### Stage 4: detailed refinement

Shortlisted zones are analyzed at finer resolution using:

- parcels and minimum contiguous land area;
- zoning and land-use compatibility;
- slope and terrain;
- wetlands;
- existing development;
- sensitive receptors;
- utility capacity and interconnection feasibility;
- ownership and acquisition feasibility;
- community engagement and site-specific environmental review.

## Equity design

AERIS keeps technical suitability and community burden as separate
outputs.

A technically high-scoring location can still be blocked from
automatic recommendation by the equity gate.

Race, ethnicity, income, and language indicators are used only to
audit disparate outcomes and concentration patterns. They are not
technical suitability variables.

## Reproducibility

Each statewide build should record:

- grid configuration;
- decision-model version;
- source URLs;
- source update dates when available;
- generation timestamp;
- criterion completeness;
- technical weights;
- equity-gate policy;
- hard-exclusion policy.
