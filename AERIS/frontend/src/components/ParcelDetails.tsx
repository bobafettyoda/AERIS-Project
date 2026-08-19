import type {
  ParcelDetail,
} from "../parcelApi";


type ParcelDetailsProps = {
  parcel: ParcelDetail | null;
  loading: boolean;
};


function value(
  input: unknown,
  fallback = "Not available",
): string {
  if (
    input === null
    || input === undefined
    || input === ""
  ) {
    return fallback;
  }

  return String(input);
}


function sourceValue(
  input: unknown,
): string {
  if (
    input === null
    || input === undefined
    || input === ""
  ) {
    return "Not reported by statewide source";
  }

  return String(input);
}


function numberValue(
  input: unknown,
  digits = 2,
): string {
  if (typeof input !== "number") {
    return "Not available";
  }

  return input.toLocaleString(
    undefined,
    {
      maximumFractionDigits: digits,
    },
  );
}


function score(
  input: unknown,
): string {
  return typeof input === "number"
    ? `${Math.round(input * 100)}%`
    : "Not available";
}


export function ParcelDetails({
  parcel,
  loading,
}: ParcelDetailsProps) {
  if (loading) {
    return (
      <section className="parcel-detail-card">
        <strong>
          Loading parcel evidence…
        </strong>
      </section>
    );
  }

  if (!parcel) {
    return (
      <section className="parcel-detail-card">
        <span className="parcel-kicker">
          Parcel investigation
        </span>

        <h2>Select a parcel</h2>

        <p className="parcel-muted">
          Parcel outlines are screening
          geometry. Selecting one reveals
          its available statewide attributes
          and inherited AERIS context.
        </p>
      </section>
    );
  }

  return (
    <section className="parcel-detail-card">
      <span className="parcel-kicker">
        Parcel screening record
      </span>

      <div className="parcel-title-row">
        <div>
          <h2>{parcel.parcel_id}</h2>

          <p>
            {value(
              parcel.identity
                .property_address,
            )}
          </p>
        </div>

        <strong className="parcel-area">
          {numberValue(
            parcel.parcel
              .geometry_area_acres,
          )}
          {" ac"}
        </strong>
      </div>

      <div
        className={
          (
            "parcel-status "
            + (
              parcel.classification
                .availability_status
              === "PUBLIC_OR_INSTITUTIONAL"
                ? "blocked"
                : parcel.classification
                    .availability_status
                  === (
                    "POTENTIAL_"
                    + "FURTHER_REVIEW"
                  )
                  ? "review"
                  : "caution"
            )
          )
        }
      >
        <strong>
          {value(
            parcel.classification
              .availability_status,
          )}
        </strong>

        <p>
          {value(
            parcel.classification
              .availability_reason,
          )}
        </p>
      </div>

      <div className="parcel-stat-grid">
        <div>
          <span>County</span>
          <strong>
            {value(
              parcel.identity
                .county_name,
            )}
          </strong>
        </div>

        <div>
          <span>Statewide zoning field</span>
          <strong>
            {sourceValue(
              parcel.parcel
                .zoning_code,
            )}
          </strong>
        </div>

        <div>
          <span>Statewide land use</span>
          <strong>
            {sourceValue(
              parcel.parcel
                .land_use_description,
            )}
          </strong>
        </div>

        <div>
          <span>Data confidence</span>
          <strong>
            {value(
              parcel.classification
                .data_confidence,
            )}
          </strong>
        </div>

        <div>
          <span>Regional technical score</span>
          <strong>
            {score(
              parcel.statewide_context
                .technical_score,
            )}
          </strong>
        </div>

        <div>
          <span>Regional effective score</span>
          <strong>
            {score(
              parcel.statewide_context
                .effective_score,
            )}
          </strong>
        </div>

        <div>
          <span>Equity gate</span>
          <strong>
            {value(
              parcel.statewide_context
                .equity_gate,
            )}
          </strong>
        </div>

        <div>
          <span>Statewide cell</span>
          <strong>
            {value(
              parcel.statewide_context
                .cell_id,
            )}
          </strong>
        </div>

        <div>
          <span>
            Inside candidate zone
          </span>

          <strong>
            {numberValue(
              parcel.scope
                .overlap_area_acres,
              2,
            )}
            {" ac"}
          </strong>
        </div>

        <div>
          <span>Zone overlap</span>

          <strong>
            {
              typeof parcel.scope
                .overlap_fraction
              === "number"
                ? (
                  (
                    parcel.scope
                      .overlap_fraction
                    * 100
                  ).toFixed(1)
                  + "%"
                )
                : "Not available"
            }
          </strong>
        </div>
      </div>

      <details className="parcel-details">
        <summary>
          Source property indicators
        </summary>

        <div className="parcel-value-list">
          <div>
            <span>Year built</span>
            <strong>
              {value(
                parcel
                  .source_development_indicators[
                    "year_built"
                  ],
              )}
            </strong>
          </div>

          <div>
            <span>
              Recorded structure square feet
            </span>

            <strong>
              {numberValue(
                parcel
                  .source_development_indicators[
                    "structure_sq_ft"
                  ],
                0,
              )}
            </strong>
          </div>

          <div>
            <span>
              Appraised improvement value
            </span>

            <strong>
              {numberValue(
                parcel
                  .source_development_indicators[
                    "appraised_improvement_value"
                  ],
                0,
              )}
            </strong>
          </div>

          <div>
            <span>Public water</span>
            <strong>
              {value(
                parcel.parcel
                  .public_water_status,
              )}
            </strong>
          </div>

          <div>
            <span>Public sewer</span>
            <strong>
              {value(
                parcel.parcel
                  .public_sewer_status,
              )}
            </strong>
          </div>
        </div>
      </details>

      <div className="parcel-warning">
        <strong>
          Availability is not confirmed
        </strong>

        <p>{parcel.warning}</p>
      </div>
    </section>
  );
}
