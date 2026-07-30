import type {
  SavedCandidate,
} from "../candidates";


const CRITERIA = [
  "climate",
  "grid_infrastructure",
  "telecom_infrastructure",
  "protected_areas",
  "water_bodies",
  "population_density",
  "road_access",
  "hydro_hazard",
];


type ComparisonPanelProps = {
  candidates: SavedCandidate[];

  onSelect: (
    candidate: SavedCandidate,
  ) => void;

  onRemove: (
    candidateId: string,
  ) => void;

  onClear: () => void;
};


function label(value: string): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() +
        word.slice(1),
    )
    .join(" ");
}


function technicalScore(
  candidate: SavedCandidate,
): number | null {
  return (
    candidate.evaluation.score_summary
      .final_suitability_score ??
    candidate.evaluation.score_summary
      .provisional_normalized_score ??
    null
  );
}


function criterionScore(
  candidate: SavedCandidate,
  criterionName: string,
): number | null {
  const value =
    candidate.evaluation.criteria[
      criterionName
    ]?.normalized_score;

  return typeof value === "number"
    ? value
    : null;
}


function percent(
  value: number | null,
): string {
  return value === null
    ? "—"
    : `${Math.round(value * 100)}%`;
}


export function ComparisonPanel({
  candidates,
  onSelect,
  onRemove,
  onClear,
}: ComparisonPanelProps) {
  if (candidates.length === 0) {
    return null;
  }

  const bestTechnicalScore = Math.max(
    ...candidates
      .map(technicalScore)
      .filter(
        (value): value is number =>
          value !== null,
      ),
  );

  const bestCandidate =
    candidates.find(
      (candidate) =>
        technicalScore(candidate) ===
        bestTechnicalScore,
    ) ?? null;

  return (
    <section className="comparison-panel">
      <div className="comparison-heading">
        <div>
          <p className="section-label">
            Saved analysis
          </p>

          <h2>
            Candidate comparison
          </h2>
        </div>

        <button
          type="button"
          className="text-button danger-text"
          onClick={onClear}
        >
          Clear all
        </button>
      </div>

      {bestCandidate && (
        <div className="comparison-summary">
          <strong>
            Highest technical score:
            {" "}
            Candidate {
              bestCandidate.label
            }
          </strong>

          <span>
            {percent(
              technicalScore(
                bestCandidate
              ),
            )}
          </span>
        </div>
      )}

      <div className="candidate-chip-row">
        {candidates.map(
          (candidate) => (
            <article
              className="candidate-chip"
              key={candidate.id}
            >
              <button
                type="button"
                className="candidate-select"
                onClick={() => {
                  onSelect(candidate);
                }}
              >
                <span className="candidate-letter">
                  {candidate.label}
                </span>

                <span>
                  <strong>
                    {candidate.name}
                  </strong>

                  <small>
                    {candidate.point.lat.toFixed(
                      4
                    )}
                    ,{" "}
                    {candidate.point.lon.toFixed(
                      4
                    )}
                  </small>
                </span>
              </button>

              <button
                type="button"
                className="candidate-remove"
                aria-label={
                  `Remove ${candidate.name}`
                }
                onClick={() => {
                  onRemove(candidate.id);
                }}
              >
                ×
              </button>
            </article>
          ),
        )}
      </div>

      {candidates.length < 2 ? (
        <p className="comparison-empty">
          Save one more evaluated location
          to activate side-by-side comparison.
        </p>
      ) : (
        <div className="comparison-table-wrap">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Measure</th>

                {candidates.map(
                  (candidate) => (
                    <th key={candidate.id}>
                      {candidate.label}
                    </th>
                  ),
                )}
              </tr>
            </thead>

            <tbody>
              <tr>
                <th>
                  Technical suitability
                </th>

                {candidates.map(
                  (candidate) => {
                    const score =
                      technicalScore(
                        candidate
                      );

                    return (
                      <td
                        className={
                          score ===
                          bestTechnicalScore
                            ? "best-cell"
                            : undefined
                        }
                        key={candidate.id}
                      >
                        {percent(score)}
                      </td>
                    );
                  },
                )}
              </tr>

              <tr>
                <th>
                  Equity gate
                </th>

                {candidates.map(
                  (candidate) => (
                    <td key={candidate.id}>
                      {candidate.equity
                        ?.gate_status ??
                        "Unavailable"}
                    </td>
                  ),
                )}
              </tr>

              <tr>
                <th>
                  Auto-recommendation
                </th>

                {candidates.map(
                  (candidate) => (
                    <td key={candidate.id}>
                      {candidate.equity
                        ?.auto_recommendation_eligible
                        ? "Eligible"
                        : "Not eligible"}
                    </td>
                  ),
                )}
              </tr>

              <tr>
                <th>
                  Hard excluded
                </th>

                {candidates.map(
                  (candidate) => (
                    <td key={candidate.id}>
                      {candidate.evaluation
                        .decision
                        .hard_excluded
                        ? "Yes"
                        : "No"}
                    </td>
                  ),
                )}
              </tr>

              {CRITERIA.map(
                (criterionName) => {
                  const values =
                    candidates.map(
                      (candidate) =>
                        criterionScore(
                          candidate,
                          criterionName,
                        ),
                    );

                  const available =
                    values.filter(
                      (
                        value
                      ): value is number =>
                        value !== null,
                    );

                  const best =
                    available.length > 0
                      ? Math.max(
                          ...available
                        )
                      : null;

                  return (
                    <tr key={criterionName}>
                      <th>
                        {label(
                          criterionName
                        )}
                      </th>

                      {candidates.map(
                        (
                          candidate,
                          index,
                        ) => (
                          <td
                            className={
                              best !== null &&
                              values[index] ===
                                best
                                ? "best-cell"
                                : undefined
                            }
                            key={
                              candidate.id
                            }
                          >
                            {percent(
                              values[index]
                            )}
                          </td>
                        ),
                      )}
                    </tr>
                  );
                },
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="comparison-disclaimer">
        Technical scores do not override
        exclusions or the separate community-
        burden safeguard.
      </p>
    </section>
  );
}
