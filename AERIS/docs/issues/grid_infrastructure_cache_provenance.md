# Grid infrastructure cached-run provenance

The statewide grid-infrastructure pipeline currently reports
`source_object_count` as the cached Maryland snapshot feature count when
`used_cache=true`.

Observed cached snapshots:

- substations: 948 Maryland features
- transmission lines: 1,003 Maryland features

The earlier live source query reported larger upstream object counts.
The cached spatial data are intact; this affects provenance semantics in
the generated manifest, not scoring or spatial coverage.

Before a future provenance-hardening release, persist the upstream
source count alongside each raw snapshot so cached and live runs use the
same definition of `source_object_count`.
