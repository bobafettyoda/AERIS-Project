import type { ParcelDetail } from "../../parcelApi";
import { distance, numberValue, value } from "./format";


export function GridContextEvidence({ parcel }: { parcel: ParcelDetail }) {
  const grid = parcel.grid_feasibility;
  if (!grid) {
    return null;
  }

  return (
    <section className="parcel-evidence-section">
      <h3 className="parcel-grid-heading">Public mapped-grid context</h3>
      <div className="parcel-grid-context-card">
        <strong>{value(grid.public_grid_context_class)}</strong>
        <span>Data confidence: {value(grid.grid_data_confidence)}</span>
      </div>
      <div className="parcel-stat-grid">
        <div><span>Nearest transmission</span><strong>{distance(grid.nearest_transmission.distance_m)}</strong></div>
        <div><span>Nearest line voltage</span><strong>{numberValue(grid.nearest_transmission.voltage_kv, 0)} kV</strong></div>
        <div><span>Line voltage class</span><strong>{value(grid.nearest_transmission.voltage_class)}</strong></div>
        <div><span>Line owner</span><strong>{value(grid.nearest_transmission.owner)}</strong></div>
        <div><span>Lines within 5 km</span><strong>{numberValue(grid.transmission_within_5km.feature_count, 0)}</strong></div>
        <div><span>Maximum mapped voltage within 5 km</span><strong>{numberValue(grid.transmission_within_5km.maximum_voltage_kv, 0)} kV</strong></div>
        <div><span>Nearest substation</span><strong>{distance(grid.nearest_substation.distance_m)}</strong></div>
        <div><span>Substation maximum voltage</span><strong>{numberValue(grid.nearest_substation.maximum_voltage_kv, 0)} kV</strong></div>
        <div><span>Substations within 10 km</span><strong>{numberValue(grid.substations_within_10km.feature_count, 0)}</strong></div>
        <div><span>Capacity status</span><strong>{value(grid.capacity.status)}</strong></div>
      </div>
      <div className="parcel-grid-warning">
        <strong>Capacity is not confirmed</strong>
        <p>{grid.warning} Utility confirmation and a formal interconnection or service study remain required.</p>
      </div>
    </section>
  );
}
