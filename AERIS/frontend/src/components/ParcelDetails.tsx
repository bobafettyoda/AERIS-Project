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

      {parcel.development_envelope && (
        <>
          <h3 className="parcel-envelope-heading">
            Preliminary mapped-constraint envelope
          </h3>

          <div className="parcel-stat-grid">
            <div>
              <span>
                Scope analysis area
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .analysis_area_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>

            <div>
              <span>
                Unique mapped constraints
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .mapped_constrained_area_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>

            <div>
              <span>
                Preliminary unconstrained
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .preliminary_unconstrained_area_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>

            <div>
              <span>
                Unconstrained fraction
              </span>

              <strong>
                {
                  typeof parcel
                    .development_envelope
                    .preliminary_unconstrained_fraction
                  === "number"
                    ? (
                      (
                        parcel
                          .development_envelope
                          .preliminary_unconstrained_fraction
                        * 100
                      ).toFixed(1)
                      + "%"
                    )
                    : "Not available"
                }
              </strong>
            </div>

            <div>
              <span>
                Largest contiguous area
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .largest_contiguous_unconstrained_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>

            <div>
              <span>
                Envelope components
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .unconstrained_component_count,
                  0,
                )}
              </strong>
            </div>

            <div>
              <span>
                Physical runway conflict
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .aviation_overlap_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>

            <div>
              <span>
                FAA notice screening overlap
              </span>

              <strong>
                {numberValue(
                  parcel
                    .development_envelope
                    .aviation_notice_screening_overlap_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>
          </div>

          <div className="parcel-envelope-warning">
            This is not confirmed buildable
            land. Buildings, wetlands, local
            setbacks, utilities, ownership,
            and entitlement review remain
            outstanding.
          </div>

          {
            parcel.development_envelope
              .aviation_notice_screening_status
            === (
              "PROPOSED_HEIGHT_REQUIRED_"
              + "FOR_PART77_SCREEN"
            )
            && (
              <div className="parcel-aviation-warning">
                <strong>
                  FAA height screening needed
                </strong>

                <p>
                  This parcel overlaps the FAA
                  Part 77 horizontal notice-
                  distance screen. Proposed
                  structure height and formal
                  FAA pre-screening are required
                  before drawing a regulatory
                  conclusion.
                </p>
              </div>
            )
          }
        </>
      )}

      {parcel.grid_feasibility && (
        <>
          <h3 className="parcel-grid-heading">
            Public mapped-grid context
          </h3>

          <div className="parcel-grid-context-card">
            <strong>
              {value(
                parcel.grid_feasibility
                  .public_grid_context_class,
              )}
            </strong>

            <span>
              Data confidence: {
                value(
                  parcel.grid_feasibility
                    .grid_data_confidence,
                )
              }
            </span>
          </div>

          <div className="parcel-stat-grid">
            <div>
              <span>
                Nearest transmission
              </span>

              <strong>
                {
                  typeof parcel
                    .grid_feasibility
                    .nearest_transmission
                    .distance_m
                  === "number"
                    ? (
                      parcel
                        .grid_feasibility
                        .nearest_transmission
                        .distance_m
                      >= 1000
                        ? (
                          (
                            parcel
                              .grid_feasibility
                              .nearest_transmission
                              .distance_m
                            / 1000
                          ).toFixed(2)
                          + " km"
                        )
                        : (
                          Math.round(
                            parcel
                              .grid_feasibility
                              .nearest_transmission
                              .distance_m
                          )
                          + " m"
                        )
                    )
                    : "Not available"
                }
              </strong>
            </div>

            <div>
              <span>
                Nearest line voltage
              </span>

              <strong>
                {numberValue(
                  parcel.grid_feasibility
                    .nearest_transmission
                    .voltage_kv,
                  0,
                )}
                {" kV"}
              </strong>
            </div>

            <div>
              <span>
                Line voltage class
              </span>

              <strong>
                {value(
                  parcel.grid_feasibility
                    .nearest_transmission
                    .voltage_class,
                )}
              </strong>
            </div>

            <div>
              <span>
                Line owner
              </span>

              <strong>
                {value(
                  parcel.grid_feasibility
                    .nearest_transmission
                    .owner,
                )}
              </strong>
            </div>

            <div>
              <span>
                Lines within 5 km
              </span>

              <strong>
                {numberValue(
                  parcel.grid_feasibility
                    .transmission_within_5km
                    .feature_count,
                  0,
                )}
              </strong>
            </div>

            <div>
              <span>
                Maximum mapped voltage
                within 5 km
              </span>

              <strong>
                {numberValue(
                  parcel.grid_feasibility
                    .transmission_within_5km
                    .maximum_voltage_kv,
                  0,
                )}
                {" kV"}
              </strong>
            </div>

            <div>
              <span>
                Nearest substation
              </span>

              <strong>
                {
                  typeof parcel
                    .grid_feasibility
                    .nearest_substation
                    .distance_m
                  === "number"
                    ? (
                      parcel
                        .grid_feasibility
                        .nearest_substation
                        .distance_m
                      >= 1000
                        ? (
                          (
                            parcel
                              .grid_feasibility
                              .nearest_substation
                              .distance_m
                            / 1000
                          ).toFixed(2)
                          + " km"
                        )
                        : (
                          Math.round(
                            parcel
                              .grid_feasibility
                              .nearest_substation
                              .distance_m
                          )
                          + " m"
                        )
                    )
                    : "Not available"
                }
              </strong>
            </div>

            <div>
              <span>
                Substation maximum voltage
              </span>

              <strong>
                {numberValue(
                  parcel.grid_feasibility
                    .nearest_substation
                    .maximum_voltage_kv,
                  0,
                )}
                {" kV"}
              </strong>
            </div>

            <div>
              <span>
                Substations within 10 km
              </span>

              <strong>
                {numberValue(
                  parcel.grid_feasibility
                    .substations_within_10km
                    .feature_count,
                  0,
                )}
              </strong>
            </div>

            <div>
              <span>
                Capacity status
              </span>

              <strong>
                {value(
                  parcel.grid_feasibility
                    .capacity.status,
                )}
              </strong>
            </div>
          </div>

          <div className="parcel-grid-warning">
            <strong>
              Capacity is not confirmed
            </strong>

            <p>
              {parcel.grid_feasibility.warning}
              {" "}
              Utility confirmation and a
              formal interconnection or
              service study remain required.
            </p>
          </div>
        </>
      )}

      {parcel.planning_context && (
        <>
          <h3 className="parcel-planning-heading">
            Planning and entitlement context
          </h3>

          <div className="parcel-planning-status">
            <strong>
              {value(
                parcel.planning_context
                  .decision
                  .planning_review_status,
              )}
            </strong>

            <span>
              Data confidence: {
                value(
                  parcel.planning_context
                    .decision
                    .data_confidence,
                )
              }
            </span>
          </div>

          <div className="parcel-stat-grid">
            <div>
              <span>
                Governing authority
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .jurisdiction
                    .authority_name,
                )}
              </strong>
            </div>

            <div>
              <span>
                Authority status
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .jurisdiction
                    .authority_status,
                )}
              </strong>
            </div>

            <div>
              <span>
                Municipality
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .jurisdiction
                    .municipality_name,
                  "Outside mapped municipality",
                )}
              </strong>
            </div>

            <div>
              <span>
                Statewide zoning code
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .zoning
                    .statewide_code,
                )}
              </strong>
            </div>

            <div>
              <span>
                Local zoning source
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .zoning
                    .local_source_status,
                )}
              </strong>
            </div>

            <div>
              <span>
                Comprehensive plan
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .planning_sources
                    .comprehensive_plan,
                )}
              </strong>
            </div>

            <div>
              <span>
                Active-development source
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .planning_sources
                    .active_development,
                )}
              </strong>
            </div>

            <div>
              <span>
                Permit source
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .planning_sources
                    .permits,
                )}
              </strong>
            </div>

            <div>
              <span>
                Priority Funding Area
              </span>

              <strong>
                {value(
                  parcel.planning_context
                    .statewide_context
                    .priority_funding_area,
                )}
              </strong>
            </div>

            <div>
              <span>
                Critical Area overlap
              </span>

              <strong>
                {numberValue(
                  parcel.planning_context
                    .statewide_context
                    .critical_area_overlap_acres,
                  2,
                )}
                {" ac"}
              </strong>
            </div>
          </div>

          <details className="parcel-details">
            <summary>
              Statewide planning overlays
            </summary>

            <div className="parcel-value-list">
              <div>
                <span>
                  Enterprise zones
                </span>

                <strong>
                  {value(
                    parcel.planning_context
                      .statewide_context
                      .enterprise_zone_names,
                    "None mapped",
                  )}
                </strong>
              </div>

              <div>
                <span>
                  Sustainable communities
                </span>

                <strong>
                  {value(
                    parcel.planning_context
                      .statewide_context
                      .sustainable_community_names,
                    "None mapped",
                  )}
                </strong>
              </div>

              <div>
                <span>
                  Foreign trade zones
                </span>

                <strong>
                  {value(
                    parcel.planning_context
                      .statewide_context
                      .foreign_trade_zone_names,
                    "None mapped",
                  )}
                </strong>
              </div>

              <div>
                <span>RISE zones</span>

                <strong>
                  {value(
                    parcel.planning_context
                      .statewide_context
                      .rise_zone_names,
                    "None mapped",
                  )}
                </strong>
              </div>

              <div>
                <span>
                  Opportunity zones
                </span>

                <strong>
                  {value(
                    parcel.planning_context
                      .statewide_context
                      .opportunity_zone_names,
                    "None mapped",
                  )}
                </strong>
              </div>
            </div>
          </details>

          <div className="parcel-planning-warning">
            <strong>
              Local verification required
            </strong>

            <p>
              {parcel.planning_context.warning}
            </p>
          </div>
        </>
      )}

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
