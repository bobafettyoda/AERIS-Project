import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  compareSiteCandidates,
  type SiteCandidate,
} from "../parcelApi";

import {
  numberValue,
  percentage,
  value,
} from "./parcel-details/format";


type SiteCandidateComparisonProps = {
  scopeId: string | null;
  candidates: SiteCandidate[];
};


function candidateLabel(
  candidate: SiteCandidate,
): string {
  if (candidate.candidate_kind
    === "MULTI_PARCEL_ASSEMBLAGE") {
    return (
      `${candidate.parcel_count ?? 0}-parcel assemblage`
    );
  }

  return candidate.parcel_id
    ?? candidate.candidate_id;
}


function siteArea(
  candidate: SiteCandidate,
): number | null {
  if (
    typeof candidate.total_site_area_acres
    === "number"
  ) {
    return candidate.total_site_area_acres;
  }

  return typeof candidate.final_site_area_acres
    === "number"
    ? candidate.final_site_area_acres
    : null;
}


export function SiteCandidateComparison({
  scopeId,
  candidates,
}: SiteCandidateComparisonProps) {
  const visibleCandidates = useMemo(
    () => candidates.slice(0, 12),
    [candidates],
  );

  const [selected, setSelected] =
    useState<string[]>([]);

  const [comparison, setComparison] =
    useState<SiteCandidate[]>([]);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    setSelected([]);
    setComparison([]);
    setError(null);
  }, [scopeId]);

  if (!scopeId || candidates.length === 0) {
    return null;
  }

  function toggleCandidate(
    candidateId: string,
  ): void {
    setComparison([]);
    setError(null);

    setSelected((current) => {
      if (current.includes(candidateId)) {
        return current.filter(
          (value) => value !== candidateId,
        );
      }

      if (current.length >= 3) {
        return current;
      }

      return [
        ...current,
        candidateId,
      ];
    });
  }

  async function compare(): Promise<void> {
    if (!scopeId) {
      setError(
        "Parcel scope is unavailable.",
      );
      return;
    }

    if (selected.length < 2) {
      setError(
        "Select two or three candidates to compare.",
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await compareSiteCandidates(
        scopeId,
        selected,
      );

      setComparison(result);
    }
    catch (caughtError: unknown) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Site candidates could not be compared.",
      );
    }
    finally {
      setLoading(false);
    }
  }

  return (
    <section className="site-candidate-card">
      <span className="parcel-kicker">
        Preliminary physical candidates
      </span>

      <h2>
        Compare parcels and assemblages
      </h2>

      <p className="parcel-muted">
        Choose up to three top candidates. The ranking is a transparent
        physical-screening aid, not an acquisition or approval decision.
      </p>

      <div className="site-candidate-list">
        {visibleCandidates.map((candidate) => {
          const checked = selected.includes(
            candidate.candidate_id,
          );

          const disabled =
            !checked
            && selected.length >= 3;

          return (
            <label
              key={candidate.candidate_id}
              className={
                checked
                  ? "site-candidate-option selected"
                  : "site-candidate-option"
              }
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => {
                  toggleCandidate(
                    candidate.candidate_id,
                  );
                }}
              />

              <span>
                <strong>
                  {candidateLabel(candidate)}
                </strong>

                <small>
                  {numberValue(
                    candidate.largest_contiguous_site_acres,
                  )}
                  {" ac contiguous · "}
                  {
                    typeof candidate.candidate_score
                    === "number"
                      ? `${Math.round(candidate.candidate_score * 100)}% screen`
                      : "score unavailable"
                  }
                </small>
              </span>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        className="site-compare-button"
        disabled={
          loading
          || selected.length < 2
        }
        onClick={() => {
          void compare();
        }}
      >
        {loading
          ? "Comparing…"
          : "Compare selected candidates"}
      </button>

      {error && (
        <p className="site-candidate-error">
          {error}
        </p>
      )}

      {comparison.length > 0 && (
        <div className="site-comparison-table-wrap">
          <table className="site-comparison-table">
            <thead>
              <tr>
                <th>Metric</th>
                {comparison.map((candidate) => (
                  <th key={candidate.candidate_id}>
                    {candidateLabel(candidate)}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              <tr>
                <th>Physical class</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {value(candidate.site_feasibility_class)}
                  </td>
                ))}
              </tr>

              <tr>
                <th>Candidate score</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {
                      typeof candidate.candidate_score
                      === "number"
                        ? `${Math.round(candidate.candidate_score * 100)}%`
                        : "—"
                    }
                  </td>
                ))}
              </tr>

              <tr>
                <th>Total site area</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {numberValue(siteArea(candidate))} ac
                  </td>
                ))}
              </tr>

              <tr>
                <th>Largest contiguous</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {numberValue(
                      candidate.largest_contiguous_site_acres,
                    )} ac
                  </td>
                ))}
              </tr>

              <tr>
                <th>Road access</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {value(candidate.road_access_status)}
                  </td>
                ))}
              </tr>

              <tr>
                <th>Wetland fraction</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {percentage(
                      candidate.mapped_wetland_fraction,
                    )}
                  </td>
                ))}
              </tr>

              <tr>
                <th>Steep-slope fraction</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {percentage(
                      candidate.steep_slope_fraction,
                    )}
                  </td>
                ))}
              </tr>

              <tr>
                <th>Building reference</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {percentage(
                      candidate.building_reference_fraction,
                    )}
                  </td>
                ))}
              </tr>

              <tr>
                <th>Redevelopment burden</th>
                {comparison.map((candidate) => (
                  <td key={candidate.candidate_id}>
                    {value(
                      candidate.redevelopment_burden_class,
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
