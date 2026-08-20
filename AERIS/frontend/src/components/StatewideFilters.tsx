import type {
  StatewideFilterState,
  StatewideSummary,
  StatewideZoneMode,
} from "../statewideApi";


type StatewideFiltersProps = {
  summary: StatewideSummary | null;
  filters: StatewideFilterState;
  zoneMode: StatewideZoneMode;
  showExcluded: boolean;
  loading: boolean;

  onFiltersChange: (
    filters: StatewideFilterState,
  ) => void;

  onZoneModeChange: (
    mode: StatewideZoneMode,
  ) => void;

  onShowExcludedChange: (
    show: boolean,
  ) => void;

  onApply: () => void;
  onReset: () => void;
};


export function StatewideFilters({
  summary,
  filters,
  zoneMode,
  showExcluded,
  loading,
  onFiltersChange,
  onZoneModeChange,
  onShowExcludedChange,
  onApply,
  onReset,
}: StatewideFiltersProps) {
  return (
    <section className="statewide-filter-card">
      <div className="statewide-section-heading">
        <div>
          <span className="statewide-kicker">
            Statewide screening
          </span>

          <h2>Heatmap controls</h2>
        </div>

        <button
          type="button"
          className="statewide-text-button"
          onClick={onReset}
        >
          Reset
        </button>
      </div>

      <label className="statewide-field">
        <span>Score surface</span>

        <select
          value={filters.scoreType}
          onChange={(event) => {
            onFiltersChange({
              ...filters,
              scoreType:
                event.target.value as StatewideFilterState["scoreType"],
            });
          }}
        >
          <option value="technical">
            Technical suitability
          </option>

          <option value="effective">
            Effective score after exclusions
          </option>
        </select>
      </label>

      <div className="statewide-two-column">
        <label className="statewide-field">
          <span>Minimum score</span>

          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={
              filters.minimumScore
            }
            onChange={(event) => {
              onFiltersChange({
                ...filters,
                minimumScore:
                  Number(
                    event.target.value
                  ),
              });
            }}
          />
        </label>

        <label className="statewide-field">
          <span>Maximum score</span>

          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={
              filters.maximumScore
            }
            onChange={(event) => {
              onFiltersChange({
                ...filters,
                maximumScore:
                  Number(
                    event.target.value
                  ),
              });
            }}
          />
        </label>
      </div>

      <label className="statewide-field">
        <span>Eligibility</span>

        <select
          value={filters.eligibility}
          onChange={(event) => {
            onFiltersChange({
              ...filters,
              eligibility:
                event.target.value as StatewideFilterState["eligibility"],
            });
          }}
        >
          <option value="all">
            All complete cells
          </option>

          <option value="auto">
            Equity PASS auto-screen cells
          </option>

          <option value="exploration">
            PASS or CAUTION exploration cells
          </option>
        </select>
      </label>

      <label className="statewide-field">
        <span>Equity gate</span>

        <select
          value={filters.equityGate}
          onChange={(event) => {
            onFiltersChange({
              ...filters,
              equityGate:
                event.target.value,
            });
          }}
        >
          <option value="">
            All equity statuses
          </option>

          <option value="PASS">
            Pass
          </option>

          <option value="CAUTION">
            Caution
          </option>

          <option value="HIGH_BURDEN">
            High burden
          </option>

          <option value="INSUFFICIENT_DATA">
            Insufficient data
          </option>
        </select>
      </label>

      <label className="statewide-field">
        <span>County</span>

        <select
          value={filters.county}
          onChange={(event) => {
            onFiltersChange({
              ...filters,
              county:
                event.target.value,
            });
          }}
        >
          <option value="">
            All Maryland counties
          </option>

          {(summary?.counties ?? []).map(
            (county) => (
              <option
                key={county.fips}
                value={county.fips}
              >
                {county.name}
              </option>
            ),
          )}
        </select>
      </label>

      <label className="statewide-field">
        <span>Exclusion status</span>

        <select
          value={filters.excluded}
          onChange={(event) => {
            onFiltersChange({
              ...filters,
              excluded:
                event.target.value as StatewideFilterState["excluded"],
            });
          }}
        >
          <option value="all">
            All cells
          </option>

          <option value="false">
            Not hard excluded
          </option>

          <option value="true">
            Hard excluded only
          </option>
        </select>
      </label>

      <div className="statewide-field">
        <span>Candidate-zone layer</span>

        <div className="statewide-segmented">
          {(
            [
              "top",
              "auto",
              "exploration",
            ] as StatewideZoneMode[]
          ).map((mode) => (
            <button
              type="button"
              key={mode}
              className={
                zoneMode === mode
                  ? "active"
                  : undefined
              }
              onClick={() => {
                onZoneModeChange(mode);
              }}
            >
              {mode === "top"
                ? "Top 5"
                : mode === "auto"
                  ? "Auto"
                  : "70–90"}
            </button>
          ))}
        </div>
      </div>

      <label className="statewide-check">
        <input
          type="checkbox"
          checked={showExcluded}
          onChange={(event) => {
            onShowExcludedChange(
              event.target.checked
            );
          }}
        />

        <span>
          Show excluded cells as a gray overlay
        </span>
      </label>

      <button
        type="button"
        className="statewide-primary-button"
        disabled={loading}
        onClick={onApply}
      >
        {loading
          ? "Updating map…"
          : "Apply heatmap filters"}
      </button>
    </section>
  );
}
