import type {
  ParcelDetail,
} from "../parcelApi";


import {
  summarizeParcel,
} from "../parcel/summaryRules";


type ParcelScreeningSummaryProps = {
  parcel: ParcelDetail;
};


export function ParcelScreeningSummary({
  parcel,
}: ParcelScreeningSummaryProps) {
  const summary = summarizeParcel(
    parcel,
  );

  return (
    <section className="parcel-screening-summary">
      <span className="parcel-kicker">
        Preliminary screening summary
      </span>

      <div className="parcel-summary-grid">
        {summary.sections.map(
          (section) => (
            <div
              key={section.label}
              className={`summary-${section.level}`}
            >
              <span>{section.label}</span>
              <strong>{section.value}</strong>
              <small>{section.detail}</small>
            </div>
          ),
        )}
      </div>

      <div
        className={`parcel-next-action summary-${summary.nextActionLevel}`}
      >
        <span>Recommended next action</span>
        <strong>
          {summary.nextAction}
        </strong>
      </div>

      <div className="parcel-summary-lists">
        <div>
          <h3>Why continue</h3>
          {summary.strengths.length > 0
            ? (
              <ul>
                {summary.strengths.map(
                  (item) => (
                    <li key={item}>{item}</li>
                  ),
                )}
              </ul>
            )
            : (
              <p>
                No strong continuation signal
                has been established yet.
              </p>
            )}
        </div>

        <div>
          <h3>What remains unresolved</h3>
          <ul>
            {summary.unresolved.map(
              (item) => (
                <li key={item}>{item}</li>
              ),
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}
