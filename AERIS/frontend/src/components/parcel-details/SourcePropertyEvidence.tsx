import type { ParcelDetail } from "../../parcelApi";
import { numberValue, value } from "./format";


export function SourcePropertyEvidence({ parcel }: { parcel: ParcelDetail }) {
  const indicators = parcel.source_development_indicators;
  return (
    <details className="parcel-details">
      <summary>Source property indicators and dates</summary>
      <div className="parcel-value-list">
        <div><span>Year built</span><strong>{value(indicators.year_built)}</strong></div>
        <div><span>Recorded structure square feet</span><strong>{numberValue(indicators.structure_sq_ft, 0)}</strong></div>
        <div><span>Appraised improvement value</span><strong>{numberValue(indicators.appraised_improvement_value, 0)}</strong></div>
        <div><span>Public water</span><strong>{value(parcel.parcel.public_water_status)}</strong></div>
        <div><span>Public sewer</span><strong>{value(parcel.parcel.public_sewer_status)}</strong></div>
        {Object.entries(parcel.source_dates).map(([key, date]) => (
          <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value(date)}</strong></div>
        ))}
      </div>
    </details>
  );
}
