import type {
  ViabilityScopeEvaluation,
} from "../viabilityApi";


type Props = {
  evaluation: ViabilityScopeEvaluation | null;
  loading: boolean;
  error: string | null;
};


function label(value: string): string {
  return value
    .toLowerCase()
    .split("_").join(" ")
    .replace(/^./, (character) => character.toUpperCase());
}


function reasonRows(values: Record<string, number>): Array<[string, number]> {
  return Object.entries(values)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5);
}


export function ViabilitySummary({
  evaluation,
  loading,
  error,
}: Props) {
  if (loading) {
    return (
      <section className="viability-card">
        <span className="parcel-kicker">Viability engine</span>
        <h2>Applying feasibility gates…</h2>
      </section>
    );
  }

  if (error) {
    return (
      <section className="viability-card viability-warning">
        <span className="parcel-kicker">Viability engine</span>
        <h2>Viability result unavailable</h2>
        <p>{error}</p>
      </section>
    );
  }

  if (!evaluation) {
    return null;
  }

  const rejected = reasonRows(evaluation.rejection_reason_counts);
  const holds = reasonRows(evaluation.hold_reason_counts);

  return (
    <section className="viability-card">
      <span className="parcel-kicker">Viability engine</span>
      <h2>{label(evaluation.scope_status)}</h2>

      <div className="viability-counts">
        <div>
          <strong>{evaluation.counts.comparison_eligible}</strong>
          <span>advance</span>
        </div>
        <div>
          <strong>{evaluation.counts.evidence_hold}</strong>
          <span>evidence hold</span>
        </div>
        <div>
          <strong>{evaluation.counts.rejected}</strong>
          <span>rejected</span>
        </div>
      </div>

      {rejected.length > 0 && (
        <div className="viability-reasons">
          <strong>Leading rejection reasons</strong>
          {rejected.map(([reason, count]) => (
            <div key={reason}>
              <span>{label(reason)}</span>
              <b>{count}</b>
            </div>
          ))}
        </div>
      )}

      {holds.length > 0 && (
        <div className="viability-reasons">
          <strong>Evidence holds</strong>
          {holds.map(([reason, count]) => (
            <div key={reason}>
              <span>{label(reason)}</span>
              <b>{count}</b>
            </div>
          ))}
        </div>
      )}

      <p className="parcel-muted">
        Only candidates that pass the configured land, environmental,
        road, grid-context, and evidence gates are sent to comparison.
        Utility capacity and local entitlement remain due-diligence items.
      </p>
    </section>
  );
}
