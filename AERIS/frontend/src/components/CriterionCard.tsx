import type { CriterionResult } from "../api";

import {
  criterionLimitations,
  evidenceRows,
} from "../evidence";


type CriterionCardProps = {
  criterionName: string;
  criterion: CriterionResult | undefined;
  canShowOnMap?: boolean;
  onShowOnMap?: () => void;
};


function formatLabel(value: string): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() +
        word.slice(1),
    )
    .join(" ");
}


function formatScore(
  score: number | null | undefined,
): string {
  if (score === null || score === undefined) {
    return "Not scored";
  }

  return `${Math.round(score * 100)}%`;
}


function readNestedString(
  value: unknown,
  ...path: string[]
): string | null {
  let current = value;

  for (const key of path) {
    if (
      typeof current !== "object" ||
      current === null ||
      Array.isArray(current)
    ) {
      return null;
    }

    current = (
      current as Record<string, unknown>
    )[key];
  }

  return typeof current === "string"
    ? current
    : null;
}


function sourceLabel(
  criterionName: string,
  criterion: CriterionResult | undefined,
): string {
  if (criterion?.source_layer) {
    return criterion.source_layer;
  }

  if (criterionName === "grid_infrastructure") {
    const substation = readNestedString(
      criterion,
      "components",
      "substation_proximity",
      "source_layer",
    );

    const transmission = readNestedString(
      criterion,
      "components",
      "transmission_line_proximity",
      "source_layer",
    );

    if (substation && transmission) {
      return `${substation} + ${transmission}`;
    }
  }

  return "Source information unavailable";
}


export function CriterionCard({
  criterionName,
  criterion,
  canShowOnMap = false,
  onShowOnMap,
}: CriterionCardProps) {
  const numericScore =
    typeof criterion?.normalized_score === "number"
      ? criterion.normalized_score
      : null;

  const rows = criterion
    ? evidenceRows(
        criterionName,
        criterion,
      )
    : [];

  const limitations = criterion
    ? criterionLimitations(criterion)
    : [];

  return (
    <details className="criterion-card">
      <summary className="criterion-summary">
        <div className="criterion-main">
          <div className="criterion-header">
            <h3>{formatLabel(criterionName)}</h3>

            <span
              className={
                criterion?.excluded
                  ? "criterion-state excluded"
                  : "criterion-state"
              }
            >
              {criterion?.excluded
                ? "Excluded"
                : criterion?.status ?? "Unknown"}
            </span>
          </div>

          <div className="criterion-score-row">
            <div className="criterion-score">
              {formatScore(numericScore)}
            </div>

            <div className="evidence-toggle">
              <span className="view-evidence">
                View evidence
              </span>

              <span className="hide-evidence">
                Hide evidence
              </span>

              <span className="evidence-chevron">
                ▼
              </span>
            </div>
          </div>

          <div className="mini-track">
            <div
              style={{
                width:
                  numericScore === null
                    ? "0%"
                    : `${Math.round(
                        numericScore * 100,
                      )}%`,
              }}
            />
          </div>

          <p className="criterion-source">
            {sourceLabel(
              criterionName,
              criterion,
            )}
          </p>
        </div>
      </summary>

      <div className="criterion-details">
        <div className="evidence-grid">
          {rows.map((row) => (
            <div
              className="evidence-row"
              key={`${criterionName}-${row.label}`}
            >
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </div>

        {canShowOnMap && onShowOnMap && (
          <button
            type="button"
            className="show-map-evidence"
            onClick={onShowOnMap}
          >
            Show evidence on map
          </button>
        )}

        {criterion?.methodology && (
          <div className="methodology-block">
            <span>Scoring method</span>

            <strong>
              {formatLabel(
                criterion.methodology,
              )}
            </strong>
          </div>
        )}

        {limitations.length > 0 && (
          <div className="limitations-block">
            <span>Screening limitations</span>

            <ul>
              {limitations.map(
                (limitation) => (
                  <li key={limitation}>
                    {limitation}
                  </li>
                ),
              )}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
