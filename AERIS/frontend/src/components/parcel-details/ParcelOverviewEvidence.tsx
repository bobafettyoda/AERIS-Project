import type { ParcelDetail } from "../../parcelApi";
import {
  numberValue,
  percentage,
  score,
  sourceValue,
  value,
} from "./format";


export function ParcelOverviewEvidence({ parcel }: { parcel: ParcelDetail }) {
  const availability = parcel.classification.availability_status;
  const level = availability === "PUBLIC_OR_INSTITUTIONAL"
    ? "blocked"
    : availability === "POTENTIAL_FURTHER_REVIEW"
      ? "review"
      : "caution";

  return (
    <>
      <div className={`parcel-status ${level}`}>
        <strong>{value(availability)}</strong>
        <p>{value(parcel.classification.availability_reason)}</p>
      </div>

      <div className="parcel-stat-grid">
        <div><span>County</span><strong>{value(parcel.identity.county_name)}</strong></div>
        <div><span>Statewide zoning field</span><strong>{sourceValue(parcel.parcel.zoning_code)}</strong></div>
        <div><span>Statewide land use</span><strong>{sourceValue(parcel.parcel.land_use_description)}</strong></div>
        <div><span>Data confidence</span><strong>{value(parcel.classification.data_confidence)}</strong></div>
        <div><span>Regional technical score</span><strong>{score(parcel.statewide_context.technical_score)}</strong></div>
        <div><span>Regional effective score</span><strong>{score(parcel.statewide_context.effective_score)}</strong></div>
        <div><span>Equity gate</span><strong>{value(parcel.statewide_context.equity_gate)}</strong></div>
        <div><span>Statewide cell</span><strong>{value(parcel.statewide_context.cell_id)}</strong></div>
        <div><span>Inside candidate zone</span><strong>{numberValue(parcel.scope.overlap_area_acres)} ac</strong></div>
        <div><span>Zone overlap</span><strong>{percentage(parcel.scope.overlap_fraction)}</strong></div>
      </div>

      <details className="parcel-details">
        <summary>Classification evidence</summary>
        <div className="parcel-value-list">
          <div><span>Public classification</span><strong>{value(parcel.classification.public_classification_evidence, "No public rule matched")}</strong></div>
          <div><span>Institutional classification</span><strong>{value(parcel.classification.institutional_classification_evidence, "No institutional rule matched")}</strong></div>
          <div><span>Existing-development indicator</span><strong>{value(parcel.classification.existing_development_indicator)}</strong></div>
          <div><span>Availability confirmed</span><strong>No</strong></div>
        </div>
      </details>
    </>
  );
}
