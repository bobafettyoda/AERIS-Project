import type { ParcelDetail } from "../parcelApi";
import { ParcelScreeningSummary } from "./ParcelScreeningSummary";
import { GridContextEvidence } from "./parcel-details/GridContextEvidence";
import { ParcelOverviewEvidence } from "./parcel-details/ParcelOverviewEvidence";
import { PhysicalFeasibilityEvidence } from "./parcel-details/PhysicalFeasibilityEvidence";
import { PlanningContextEvidence } from "./parcel-details/PlanningContextEvidence";
import { SiteFeasibilityEvidence } from "./parcel-details/SiteFeasibilityEvidence";
import { SourcePropertyEvidence } from "./parcel-details/SourcePropertyEvidence";
import { numberValue, value } from "./parcel-details/format";


type ParcelDetailsProps = {
  parcel: ParcelDetail | null;
  loading: boolean;
};


export function ParcelDetails({ parcel, loading }: ParcelDetailsProps) {
  if (loading) {
    return <section className="parcel-detail-card"><strong>Loading parcel evidence…</strong></section>;
  }

  if (!parcel) {
    return (
      <section className="parcel-detail-card">
        <span className="parcel-kicker">Parcel investigation</span>
        <h2>Select a parcel</h2>
        <p className="parcel-muted">Parcel outlines are screening geometry. Select one to review regional, mapped constraints, physical site feasibility, grid, and planning evidence.</p>
      </section>
    );
  }

  return (
    <section className="parcel-detail-card">
      <span className="parcel-kicker">Parcel screening record</span>
      <div className="parcel-title-row">
        <div>
          <h2>{parcel.parcel_id}</h2>
          <p>{value(parcel.identity.property_address)}</p>
        </div>
        <strong className="parcel-area">{numberValue(parcel.parcel.geometry_area_acres)} ac</strong>
      </div>

      <ParcelScreeningSummary parcel={parcel} />

      <details className="parcel-details parcel-all-evidence">
        <summary>Open detailed evidence</summary>
        <ParcelOverviewEvidence parcel={parcel} />
        <PhysicalFeasibilityEvidence parcel={parcel} />
        <SiteFeasibilityEvidence parcel={parcel} />
        <GridContextEvidence parcel={parcel} />
        <PlanningContextEvidence parcel={parcel} />
        <SourcePropertyEvidence parcel={parcel} />
        <div className="parcel-warning">
          <strong>Availability is not confirmed</strong>
          <p>{parcel.warning}</p>
        </div>
      </details>
    </section>
  );
}
