import type {
  StatewideCellDetail,
  StatewideSummary,
  StatewideZoneDetail,
} from "../statewideApi";


type StatewideDetailsProps = {
  summary: StatewideSummary | null;
  cell: StatewideCellDetail | null;
  zone: StatewideZoneDetail | null;
  loading: boolean;
};


function percentage(
  value: unknown,
): string {
  return typeof value === "number"
    ? `${Math.round(value * 100)}%`
    : "Not available";
}


function numberValue(
  value: unknown,
  digits = 0,
): string {
  return typeof value === "number"
    ? value.toLocaleString(
        undefined,
        {
          maximumFractionDigits:
            digits,
        },
      )
    : "Not available";
}


function distance(
  value: unknown,
): string {
  if (typeof value !== "number") {
    return "Not available";
  }

  if (value >= 1000) {
    return `${(
      value / 1000
    ).toFixed(2)} km`;
  }

  return `${Math.round(value)} m`;
}


function label(
  value: string,
): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase()
        + word.slice(1),
    )
    .join(" ");
}


export function StatewideDetails({
  summary,
  cell,
  zone,
  loading,
}: StatewideDetailsProps) {
  if (loading) {
    return (
      <section className="statewide-detail-card">
        <div className="statewide-loading-row">
          <span className="statewide-spinner" />

          <div>
            <strong>
              Loading statewide evidence
            </strong>

            <p>
              Reading the selected grid cell
              or candidate zone.
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (zone) {
    const properties =
      zone.properties ?? {};

    return (
      <section className="statewide-detail-card">
        <span className="statewide-kicker">
          Regional screening candidate zone
        </span>

        <div className="statewide-detail-title">
          <div>
            <h2>{zone.zone_id}</h2>

            <p>
              {String(
                properties[
                  "dominant_county"
                ]
                ?? "Maryland",
              )}
            </p>
          </div>

          <strong className="statewide-large-score">
            {percentage(
              properties[
                "mean_score"
              ],
            )}
          </strong>
        </div>

        <div className="statewide-stat-grid">
          <div>
            <span>Maximum score</span>
            <strong>
              {percentage(
                properties[
                  "maximum_score"
                ],
              )}
            </strong>
          </div>

          <div>
            <span>90th percentile</span>
            <strong>
              {percentage(
                properties[
                  "p90_score"
                ],
              )}
            </strong>
          </div>

          <div>
            <span>Zone area</span>
            <strong>
              {numberValue(
                properties[
                  "area_sq_km"
                ],
                2,
              )} km²
            </strong>
          </div>

          <div>
            <span>Member cells</span>
            <strong>
              {
                zone.membership
                  .member_count
              }
            </strong>
          </div>
        </div>

        <div className="statewide-warning-card">
          <strong>
            Screening zone—not an approved site
          </strong>

          <p>
            {zone.interpretation}
          </p>
        </div>

        <details className="statewide-details">
          <summary>
            Zone composition
          </summary>

          <h3>Equity-gate composition</h3>

          <div className="statewide-value-list">
            {Object.entries(
              zone.member_summary
                .equity_gate_counts
                ?? {},
            ).map(
              ([key, value]) => (
                <div key={key}>
                  <span>
                    {label(key)}
                  </span>

                  <strong>
                    {value}
                  </strong>
                </div>
              ),
            )}
          </div>

          <h3>County composition</h3>

          <div className="statewide-value-list">
            {Object.entries(
              zone.member_summary
                .county_counts
                ?? {},
            ).map(
              ([key, value]) => (
                <div key={key}>
                  <span>{key}</span>
                  <strong>
                    {value}
                  </strong>
                </div>
              ),
            )}
          </div>
        </details>
      </section>
    );
  }

  if (cell) {
    const communityImpact =
      cell.community_impact ?? {};

    const exclusionReasons =
      cell.decision
        .exclusion_reasons ?? [];

    const criteria =
      cell.scores.criteria ?? {};

    const evidence =
      cell.evidence ?? {};

    const gridEvidence =
      evidence.grid ?? {};

    const roadEvidence =
      evidence.road ?? {};

    const telecomEvidence =
      evidence.telecom ?? {};

    const environmentEvidence =
      evidence.environment ?? {};

    return (
      <section className="statewide-detail-card">
        <span className="statewide-kicker">
          Statewide grid cell
        </span>

        <div className="statewide-detail-title">
          <div>
            <h2>{cell.cell_id}</h2>

            <p>
              {
                cell.location
                  .county_name
                ?? "Maryland"
              }
            </p>
          </div>

          <strong className="statewide-large-score">
            {percentage(
              cell.scores
                .technical_suitability,
            )}
          </strong>
        </div>

        <div className="statewide-stat-grid">
          <div>
            <span>Technical score</span>
            <strong>
              {percentage(
                cell.scores
                  .technical_suitability,
              )}
            </strong>
          </div>

          <div>
            <span>
              Effective score
            </span>
            <strong>
              {percentage(
                cell.scores
                  .effective_suitability,
              )}
            </strong>
          </div>

          <div>
            <span>Equity gate</span>
            <strong>
              {String(
                communityImpact[
                  "equity_gate"
                ]
                ?? "Unavailable",
              )}
            </strong>
          </div>

          <div>
            <span>Model status</span>
            <strong>
              {
                cell.decision
                  .model_status
                ?? "Unavailable"
              }
            </strong>
          </div>
        </div>

        {cell.decision
          .hard_excluded && (
          <div className="statewide-danger-card">
            <strong>
              Hard excluded
            </strong>

            <p>
              {
                exclusionReasons
                  .join(", ")
              }
            </p>
          </div>
        )}

        <h3 className="statewide-subheading">
          Eight technical criteria
        </h3>

        <div className="statewide-criteria-grid">
          {Object.entries(
            criteria,
          ).map(([key, value]) => (
            <div key={key}>
              <span>
                {label(key)}
              </span>

              <strong>
                {percentage(value)}
              </strong>
            </div>
          ))}
        </div>

        <details className="statewide-details">
          <summary>
            Infrastructure and environmental evidence
          </summary>

          <div className="statewide-value-list">
            <div>
              <span>
                Nearest substation
              </span>

              <strong>
                {distance(
                  gridEvidence[
                    "substation_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Nearest transmission line
              </span>

              <strong>
                {distance(
                  gridEvidence[
                    "transmission_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Major-route distance
              </span>

              <strong>
                {distance(
                  roadEvidence[
                    "major_road_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Fiber-coverage distance
              </span>

              <strong>
                {distance(
                  telecomEvidence[
                    "fiber_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Fiber providers within 5 km
              </span>

              <strong>
                {numberValue(
                  telecomEvidence[
                    "provider_count_5km"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Surface-water distance
              </span>

              <strong>
                {distance(
                  environmentEvidence[
                    "water_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                Protected-land distance
              </span>

              <strong>
                {distance(
                  environmentEvidence[
                    "protected_distance_m"
                  ],
                )}
              </strong>
            </div>

            <div>
              <span>
                SFHA distance
              </span>

              <strong>
                {distance(
                  environmentEvidence[
                    "sfha_distance_m"
                  ],
                )}
              </strong>
            </div>
          </div>
        </details>

        <details className="statewide-details">
          <summary>
            Community-impact audit fields
          </summary>

          <p className="statewide-muted-copy">
            These fields audit disparate
            outcomes. They do not increase
            technical suitability.
          </p>

          <div className="statewide-value-list">
            {Object.entries(
              communityImpact,
            )
              .filter(
                ([key]) =>
                  key !==
                  "used_in_technical_score",
              )
              .map(
                ([key, value]) => (
                  <div key={key}>
                    <span>
                      {label(key)}
                    </span>

                    <strong>
                      {typeof value ===
                      "number"
                        ? numberValue(
                            value,
                            1,
                          )
                        : String(
                            value
                            ?? "Unavailable",
                          )}
                    </strong>
                  </div>
                ),
              )}
          </div>
        </details>
      </section>
    );
  }

  return (
    <section className="statewide-detail-card">
      <span className="statewide-kicker">
        Maryland statewide model
      </span>

      <h2>
        Select a heatmap cell or candidate zone
      </h2>

      <p className="statewide-muted-copy">
        The heatmap shows complete
        eight-criterion technical screening.
        Environmental exclusions and equity
        gates remain separate safeguards.
      </p>

      {summary && (
        <>
          <div className="statewide-stat-grid">
            <div>
              <span>Total cells</span>
              <strong>
                {
                  summary.grid
                    .cell_count
                .toLocaleString()
                }
              </strong>
            </div>

            <div>
              <span>Hard excluded</span>
              <strong>
                {
                  summary.grid
                    .hard_excluded_cells
                    .toLocaleString()
                }
              </strong>
            </div>

            <div>
              <span>Auto-screen eligible</span>
              <strong>
                {
                  summary.grid
                    .auto_screen_eligible_cells
                    .toLocaleString()
                }
              </strong>
            </div>

            <div>
              <span>Exploration eligible</span>
              <strong>
                {
                  summary.grid
                    .exploration_screen_eligible_cells
                    .toLocaleString()
                }
              </strong>
            </div>
          </div>

          <div
            className={
              summary.audit.status
              === "PASS"
                ? "statewide-audit-card pass"
                : "statewide-audit-card"
            }
          >
            <strong>
              Bias audit: {
                summary.audit.status
              }
            </strong>

            <p>
              Release status: {
                summary.audit
                  .release_status
              }
            </p>
          </div>
        </>
      )}
    </section>
  );
}
