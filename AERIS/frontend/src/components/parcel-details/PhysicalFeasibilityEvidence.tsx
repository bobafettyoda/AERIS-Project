import type { ParcelDetail } from "../../parcelApi";
import { numberValue, percentage, value } from "./format";


export function PhysicalFeasibilityEvidence({ parcel }: { parcel: ParcelDetail }) {
  const envelope = parcel.development_envelope;
  if (!envelope) {
    return null;
  }

  return (
    <section className="parcel-evidence-section">
      <h3 className="parcel-envelope-heading">Preliminary mapped-constraint envelope</h3>
      <div className="parcel-stat-grid">
        <div><span>Scope analysis area</span><strong>{numberValue(envelope.analysis_area_acres)} ac</strong></div>
        <div><span>Unique mapped constraints</span><strong>{numberValue(envelope.mapped_constrained_area_acres)} ac</strong></div>
        <div><span>Preliminary unconstrained</span><strong>{numberValue(envelope.preliminary_unconstrained_area_acres)} ac</strong></div>
        <div><span>Unconstrained fraction</span><strong>{percentage(envelope.preliminary_unconstrained_fraction)}</strong></div>
        <div><span>Largest contiguous area</span><strong>{numberValue(envelope.largest_contiguous_unconstrained_acres)} ac</strong></div>
        <div><span>Envelope components</span><strong>{numberValue(envelope.unconstrained_component_count, 0)}</strong></div>
        <div><span>Physical runway conflict</span><strong>{numberValue(envelope.aviation_overlap_acres)} ac</strong></div>
        <div><span>FAA notice-screen overlap</span><strong>{numberValue(envelope.aviation_notice_screening_overlap_acres)} ac</strong></div>
      </div>

      <details className="parcel-details">
        <summary>Constraint breakdown</summary>
        <div className="parcel-value-list">
          <div><span>Water overlap</span><strong>{numberValue(envelope.water_overlap_acres)} ac</strong></div>
          <div><span>Protected-land overlap</span><strong>{numberValue(envelope.protected_lands_overlap_acres)} ac</strong></div>
          <div><span>SFHA overlap</span><strong>{numberValue(envelope.sfha_overlap_acres)} ac</strong></div>
          <div><span>Mapped constraint types</span><strong>{value(envelope.mapped_constraint_types, "None mapped")}</strong></div>
        </div>
      </details>

      <div className="parcel-envelope-warning">
        This is not confirmed buildable land. Buildings, wetlands, terrain,
        local setbacks, access, utilities, ownership, and entitlement review
        remain outstanding.
      </div>

      {envelope.aviation_notice_screening_status === "PROPOSED_HEIGHT_REQUIRED_FOR_PART77_SCREEN" && (
        <div className="parcel-aviation-warning">
          <strong>FAA height screening needed</strong>
          <p>This parcel overlaps the horizontal Part 77 notice-distance screen. Proposed structure height and formal FAA pre-screening remain required.</p>
        </div>
      )}
    </section>
  );
}
