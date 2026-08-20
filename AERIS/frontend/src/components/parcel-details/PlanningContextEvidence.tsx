import type { ParcelDetail } from "../../parcelApi";
import { numberValue, percentage, value } from "./format";


export function PlanningContextEvidence({ parcel }: { parcel: ParcelDetail }) {
  const planning = parcel.planning_context;
  if (!planning) {
    return null;
  }

  return (
    <section className="parcel-evidence-section">
      <h3 className="parcel-planning-heading">Planning and entitlement context</h3>
      <div className="parcel-planning-status">
        <strong>{value(planning.decision.planning_review_status)}</strong>
        <span>Data confidence: {value(planning.decision.data_confidence)}</span>
      </div>
      <div className="parcel-stat-grid">
        <div><span>Governing authority</span><strong>{value(planning.jurisdiction.authority_name)}</strong></div>
        <div><span>Authority status</span><strong>{value(planning.jurisdiction.authority_status)}</strong></div>
        <div><span>Municipality</span><strong>{value(planning.jurisdiction.municipality_name, "Outside mapped municipality")}</strong></div>
        <div><span>Municipal overlap</span><strong>{numberValue(planning.jurisdiction.municipality_overlap_acres)} ac ({percentage(planning.jurisdiction.municipality_overlap_fraction)})</strong></div>
        <div><span>Statewide zoning code</span><strong>{value(planning.zoning.statewide_code)}</strong></div>
        <div><span>Local zoning source</span><strong>{value(planning.zoning.local_source_status)}</strong></div>
        <div><span>Comprehensive plan</span><strong>{value(planning.planning_sources.comprehensive_plan)}</strong></div>
        <div><span>Active-development source</span><strong>{value(planning.planning_sources.active_development)}</strong></div>
        <div><span>Permit source</span><strong>{value(planning.planning_sources.permits)}</strong></div>
        <div><span>Priority Funding Area</span><strong>{value(planning.statewide_context.priority_funding_area)}</strong></div>
        <div><span>PFA overlap</span><strong>{numberValue(planning.statewide_context.priority_funding_area_overlap_acres)} ac ({percentage(planning.statewide_context.priority_funding_area_overlap_fraction)})</strong></div>
        <div><span>Critical Area overlap</span><strong>{numberValue(planning.statewide_context.critical_area_overlap_acres)} ac</strong></div>
      </div>

      <details className="parcel-details">
        <summary>Adapter and statewide overlay evidence</summary>
        <div className="parcel-value-list">
          <div><span>Local adapter</span><strong>{value(planning.adapter.name, "No authoritative local adapter")}</strong></div>
          <div><span>Adapter status</span><strong>{value(planning.adapter.zoning_status)}</strong></div>
          <div><span>Enterprise zones</span><strong>{value(planning.statewide_context.enterprise_zone_names, "None mapped")}</strong></div>
          <div><span>Sustainable communities</span><strong>{value(planning.statewide_context.sustainable_community_names, "None mapped")}</strong></div>
          <div><span>Foreign trade zones</span><strong>{value(planning.statewide_context.foreign_trade_zone_names, "None mapped")}</strong></div>
          <div><span>RISE zones</span><strong>{value(planning.statewide_context.rise_zone_names, "None mapped")}</strong></div>
          <div><span>Opportunity zones</span><strong>{value(planning.statewide_context.opportunity_zone_names, "None mapped")}</strong></div>
        </div>
      </details>

      <div className="parcel-planning-warning">
        <strong>Local verification required</strong>
        <p>{planning.warning}</p>
      </div>
    </section>
  );
}
