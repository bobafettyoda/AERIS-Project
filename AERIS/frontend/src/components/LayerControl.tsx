import {
  EVIDENCE_GROUPS,
  type EvidenceGroup,
  type EvidenceVisibility,
} from "../mapEvidence";


type LayerControlProps = {
  visibility: EvidenceVisibility;

  onChange: (
    group: EvidenceGroup,
    visible: boolean,
  ) => void;
};


export function LayerControl({
  visibility,
  onChange,
}: LayerControlProps) {
  return (
    <details className="layer-control">
      <summary>
        Map evidence layers
      </summary>

      <div className="layer-control-body">
        {EVIDENCE_GROUPS.map(
          (group) => (
            <label
              className="layer-option"
              key={group.key}
            >
              <input
                type="checkbox"
                checked={
                  visibility[group.key]
                }
                onChange={(event) => {
                  onChange(
                    group.key,
                    event.target.checked,
                  );
                }}
              />

              <span>
                <strong>
                  {group.label}
                </strong>

                <small>
                  {group.description}
                </small>
              </span>
            </label>
          ),
        )}
      </div>
    </details>
  );
}
