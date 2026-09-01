import type {
  ArtifactStatus,
  ParcelFeatureCollection,
} from "../parcelApi";

import type {
  ParcelView,
} from "../parcel/viewLayers";


export type ZoneOption = {
  zoneId: string;
  label: string;
};


type ParcelControlsProps = {
  zoneOptions: ZoneOption[];
  selectedZoneId: string;
  loading: boolean;
  parcels: ParcelFeatureCollection | null;
  artifacts: Record<string, ArtifactStatus>;
  parcelView: ParcelView;
  onZoneChange: (zoneId: string) => void;
  onLoad: () => void;
  onViewChange: (view: ParcelView) => void;
};


const ARTIFACT_FOR_VIEW: Record<ParcelView, string> = {
  parcels: "parcels",
  envelopes: "envelopes",
  constraints: "envelopes",
  site: "site",
  grid: "grid",
  planning: "planning",
};


const VIEWS: Array<{
  id: ParcelView;
  label: string;
}> = [
  { id: "parcels", label: "Parcels" },
  { id: "envelopes", label: "Envelopes" },
  { id: "site", label: "Site" },
  { id: "constraints", label: "Constraints" },
  { id: "grid", label: "Grid" },
  { id: "planning", label: "Planning" },
];


export function ParcelControls({
  zoneOptions,
  selectedZoneId,
  loading,
  parcels,
  artifacts,
  parcelView,
  onZoneChange,
  onLoad,
  onViewChange,
}: ParcelControlsProps) {
  return (
    <section className="parcel-control-card">
      <span className="parcel-kicker">
        Candidate-zone drill-down
      </span>

      <h2>Open parcel investigation</h2>

      <label>
        <span>Candidate zone</span>

        <select
          value={selectedZoneId}
          onChange={(event) => {
            onZoneChange(
              event.target.value,
            );
          }}
        >
          {zoneOptions.map((option) => (
            <option
              key={option.zoneId}
              value={option.zoneId}
            >
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        disabled={
          loading
          || !selectedZoneId
        }
        onClick={onLoad}
      >
        {loading
          ? "Building parcel evidence…"
          : "Load parcel investigation"}
      </button>

      {parcels && (
        <div className="parcel-view-controls">
          <span>Map layer</span>

          <div>
            {VIEWS.map((view) => (
              <button
                type="button"
                key={view.id}
                disabled={
                  artifacts[
                    ARTIFACT_FOR_VIEW[view.id]
                  ]?.state !== "ready"
                }
                className={
                  parcelView === view.id
                    ? "active"
                    : undefined
                }
                title={
                  artifacts[
                    ARTIFACT_FOR_VIEW[view.id]
                  ]?.error
                  ?? undefined
                }
                onClick={() => {
                  onViewChange(view.id);
                }}
              >
                {view.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {parcels && (
        <div className="parcel-artifact-status">
          {Object.entries(artifacts).map(
            ([name, artifact]) => (
              <span
                key={name}
                className={`artifact-${artifact.state}`}
                title={
                  artifact.error
                  ?? undefined
                }
              >
                {name}: {artifact.state}
              </span>
            ),
          )}
        </div>
      )}

      {parcels && (
        <div className="parcel-scope-note">
          <strong>
            {parcels.metadata
              .returned_count
              .toLocaleString()}
            {" "}
            parcels rendered
          </strong>

          <p>
            {parcels.metadata.truncated
              ? (
                "The map response was limited for performance."
              )
              : (
                "All matching parcels are displayed."
              )}
          </p>
        </div>
      )}
    </section>
  );
}
