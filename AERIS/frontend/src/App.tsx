import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type { Geometry } from "geojson";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  API_BASE_URL,
  evaluateCandidateSite,
  evaluateEquityScreen,
  fetchMarylandBoundary,
  type CandidatePoint,
  type EquityScreenResult,
  type SiteEvaluation,
} from "./api";

import "./App.css";


const INITIAL_POINT: CandidatePoint = {
  lat: 38.9897,
  lon: -76.9378,
};


const CRITERIA = [
  "climate",
  "grid_infrastructure",
  "telecom_infrastructure",
  "protected_areas",
  "water_bodies",
  "population_density",
  "road_access",
  "hydro_hazard",
];


function formatLabel(value: string): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() +
        word.slice(1),
    )
    .join(" ");
}


function formatScore(
  score: number | null | undefined,
): string {
  if (score === null || score === undefined) {
    return "Not scored";
  }

  return `${Math.round(score * 100)}%`;
}


function formatPercent(
  value: number | null | undefined,
): string {
  if (value === null || value === undefined) {
    return "Not available";
  }

  return `${Math.round(value)}%`;
}


function extendCoordinateBounds(
  bounds: maplibregl.LngLatBounds,
  coordinates: unknown,
): void {
  if (!Array.isArray(coordinates)) {
    return;
  }

  if (
    coordinates.length >= 2 &&
    typeof coordinates[0] === "number" &&
    typeof coordinates[1] === "number"
  ) {
    bounds.extend([
      coordinates[0],
      coordinates[1],
    ]);

    return;
  }

  for (const coordinate of coordinates) {
    extendCoordinateBounds(
      bounds,
      coordinate,
    );
  }
}


function extendGeometryBounds(
  bounds: maplibregl.LngLatBounds,
  geometry: Geometry,
): void {
  if (geometry.type === "GeometryCollection") {
    for (const child of geometry.geometries) {
      extendGeometryBounds(bounds, child);
    }

    return;
  }

  extendCoordinateBounds(
    bounds,
    geometry.coordinates,
  );
}


function equityBadgeClass(
  status: EquityScreenResult["gate_status"],
): string {
  switch (status) {
    case "PASS":
      return "equity-badge pass";

    case "CAUTION":
      return "equity-badge caution";

    case "HIGH_BURDEN":
      return "equity-badge high-burden";

    default:
      return "equity-badge insufficient";
  }
}


function App() {
  const mapContainerRef =
    useRef<HTMLDivElement | null>(null);

  const mapRef =
    useRef<maplibregl.Map | null>(null);

  const markerRef =
    useRef<maplibregl.Marker | null>(null);

  const requestRef =
    useRef<AbortController | null>(null);

  const boundaryRequestRef =
    useRef<AbortController | null>(null);

  const [selectedPoint, setSelectedPoint] =
    useState<CandidatePoint>(INITIAL_POINT);

  const [evaluation, setEvaluation] =
    useState<SiteEvaluation | null>(null);

  const [equity, setEquity] =
    useState<EquityScreenResult | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const [equityError, setEquityError] =
    useState<string | null>(null);


  const placeMarker = useCallback(
    (point: CandidatePoint) => {
      const map = mapRef.current;

      if (!map) {
        return;
      }

      if (!markerRef.current) {
        markerRef.current =
          new maplibregl.Marker({
            color: "#d97706",
          })
            .setLngLat([
              point.lon,
              point.lat,
            ])
            .addTo(map);
      } else {
        markerRef.current.setLngLat([
          point.lon,
          point.lat,
        ]);
      }
    },
    [],
  );


  const evaluatePoint = useCallback(
    async (point: CandidatePoint) => {
      requestRef.current?.abort();

      const controller = new AbortController();
      requestRef.current = controller;

      setSelectedPoint(point);
      setLoading(true);
      setError(null);
      setEquityError(null);
      setEquity(null);

      try {
        const technicalResult =
          await evaluateCandidateSite(
            point,
            controller.signal,
          );

        setEvaluation(technicalResult);

        if (
          technicalResult.decision.status ===
            "outside_study_area" ||
          technicalResult.study_area
            ?.inside_study_area === false
        ) {
          return;
        }

        try {
          const equityResult =
            await evaluateEquityScreen(
              point,
              controller.signal,
            );

          setEquity(equityResult);
        } catch (caughtEquityError) {
          if (
            caughtEquityError instanceof DOMException &&
            caughtEquityError.name === "AbortError"
          ) {
            return;
          }

          const message =
            caughtEquityError instanceof Error
              ? caughtEquityError.message
              : "The equity screen failed.";

          setEquityError(message);
        }
      } catch (caughtError) {
        if (
          caughtError instanceof DOMException &&
          caughtError.name === "AbortError"
        ) {
          return;
        }

        const message =
          caughtError instanceof Error
            ? caughtError.message
            : "The candidate-site evaluation failed.";

        setEvaluation(null);
        setEquity(null);
        setError(message);
      } finally {
        if (
          requestRef.current === controller
        ) {
          requestRef.current = null;
          setLoading(false);
        }
      }
    },
    [],
  );


  useEffect(() => {
    if (
      !mapContainerRef.current ||
      mapRef.current
    ) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style:
        "https://tiles.openfreemap.org/styles/liberty",
      center: [
        INITIAL_POINT.lon,
        INITIAL_POINT.lat,
      ],
      zoom: 8,
    });

    mapRef.current = map;

    map.addControl(
      new maplibregl.NavigationControl(),
      "top-right",
    );

    const boundaryController =
      new AbortController();

    boundaryRequestRef.current =
      boundaryController;

    map.on("load", async () => {
      placeMarker(INITIAL_POINT);

      try {
        const boundary =
          await fetchMarylandBoundary(
            boundaryController.signal,
          );

        if (!map.getSource("maryland-boundary")) {
          map.addSource(
            "maryland-boundary",
            {
              type: "geojson",
              data: boundary,
            },
          );

          map.addLayer({
            id: "maryland-boundary-fill",
            type: "fill",
            source: "maryland-boundary",
            paint: {
              "fill-color": "#147d7f",
              "fill-opacity": 0.035,
            },
          });

          map.addLayer({
            id: "maryland-boundary-line",
            type: "line",
            source: "maryland-boundary",
            paint: {
              "line-color": "#d97706",
              "line-width": 3,
              "line-opacity": 0.95,
            },
          });
        }

        const bounds =
          new maplibregl.LngLatBounds();

        for (const feature of boundary.features) {
          if (feature.geometry) {
            extendGeometryBounds(
              bounds,
              feature.geometry,
            );
          }
        }

        if (!bounds.isEmpty()) {
          map.fitBounds(bounds, {
            padding: 42,
            duration: 0,
          });
        }
      } catch (boundaryError) {
        if (
          boundaryError instanceof DOMException &&
          boundaryError.name === "AbortError"
        ) {
          return;
        }

        console.error(
          "Maryland boundary failed to load:",
          boundaryError,
        );
      }
    });

    map.on(
      "click",
      (
        event: maplibregl.MapMouseEvent,
      ) => {
        const point: CandidatePoint = {
          lat: Number(
            event.lngLat.lat.toFixed(6),
          ),
          lon: Number(
            event.lngLat.lng.toFixed(6),
          ),
        };

        placeMarker(point);
        void evaluatePoint(point);
      },
    );

    return () => {
      requestRef.current?.abort();
      boundaryRequestRef.current?.abort();

      markerRef.current?.remove();
      markerRef.current = null;

      map.remove();
      mapRef.current = null;
    };
  }, [evaluatePoint, placeMarker]);


  const suitabilityScore =
    evaluation?.score_summary
      .final_suitability_score ??
    evaluation?.score_summary
      .provisional_normalized_score ??
    null;

  const scorePercent =
    suitabilityScore === null
      ? null
      : Math.round(
          suitabilityScore * 100,
        );

  const outsideStudyArea =
    evaluation?.decision.status ===
    "outside_study_area";


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">
            Maryland Data Center Siting
            Screening Tool
          </p>

          <h1>AERIS</h1>
        </div>

        <div className="connection">
          <span className="connection-dot" />
          API: {API_BASE_URL}
        </div>
      </header>

      <main className="workspace">
        <section className="map-panel">
          <div
            ref={mapContainerRef}
            className="map"
          />

          <div className="study-area-chip">
            Maryland study area
          </div>

          <div className="map-message">
            Click inside Maryland to evaluate a
            candidate location.
          </div>
        </section>

        <aside className="results-panel">
          <section className="location-card">
            <div>
              <p className="section-label">
                Selected location
              </p>

              <strong>
                {selectedPoint.lat.toFixed(5)},{" "}
                {selectedPoint.lon.toFixed(5)}
              </strong>
            </div>

            <button
              type="button"
              disabled={loading}
              onClick={() => {
                placeMarker(selectedPoint);

                void evaluatePoint(
                  selectedPoint,
                );
              }}
            >
              {loading
                ? "Evaluating..."
                : "Evaluate site"}
            </button>
          </section>

          {loading && (
            <section className="notice">
              <span className="spinner" />

              <div>
                <strong>
                  Running Maryland analysis
                </strong>

                <p>
                  Evaluating technical criteria
                  and the separate community-impact
                  safeguard.
                </p>
              </div>
            </section>
          )}

          {error && (
            <section className="notice error">
              <div>
                <strong>
                  Evaluation failed
                </strong>

                <p>{error}</p>
              </div>
            </section>
          )}

          {!loading &&
            !error &&
            !evaluation && (
              <section className="empty-state">
                <h2>
                  Evaluate the test location
                </h2>

                <p>
                  Select the button above or click
                  another Maryland location.
                </p>
              </section>
            )}

          {!loading &&
            evaluation &&
            outsideStudyArea && (
              <section className="notice error">
                <div>
                  <strong>
                    Outside the Maryland study area
                  </strong>

                  <p>
                    {evaluation.decision.message ??
                      "Select a location within Maryland."}
                  </p>
                </div>
              </section>
            )}

          {!loading &&
            evaluation &&
            !outsideStudyArea && (
              <>
                <section className="score-card">
                  <div>
                    <p className="section-label">
                      Technical suitability
                    </p>

                    <div className="score-number">
                      {scorePercent ?? "—"}
                      <span>/100</span>
                    </div>
                  </div>

                  <span
                    className={
                      evaluation.decision
                        .hard_excluded
                        ? "decision-badge excluded"
                        : "decision-badge complete"
                    }
                  >
                    {evaluation.decision
                      .hard_excluded
                      ? "Excluded"
                      : evaluation.decision.status}
                  </span>

                  <div className="score-track">
                    <div
                      className="score-fill"
                      style={{
                        width:
                          `${scorePercent ?? 0}%`,
                      }}
                    />
                  </div>

                  <p className="score-caption">
                    Technical model completion:{" "}
                    {
                      evaluation.score_summary
                        .model_completion_percent
                    }
                    %. Community burden is evaluated
                    separately and cannot improve this
                    score.
                  </p>
                </section>

                {evaluation.decision
                  .hard_excluded && (
                    <section className="notice error">
                      <div>
                        <strong>
                          Technical hard exclusion
                        </strong>

                        <p>
                          {evaluation.decision
                            .hard_exclusion_reasons
                            .map(formatLabel)
                            .join(", ")}
                        </p>
                      </div>
                    </section>
                  )}

                {equityError && (
                  <section className="notice error">
                    <div>
                      <strong>
                        Community-impact data
                        unavailable
                      </strong>

                      <p>{equityError}</p>
                    </div>
                  </section>
                )}

                {equity && (
                  <section className="equity-card">
                    <div className="equity-heading">
                      <div>
                        <p className="section-label">
                          Community impact and equity
                        </p>

                        <h2>
                          Environmental-justice gate
                        </h2>
                      </div>

                      <span
                        className={equityBadgeClass(
                          equity.gate_status,
                        )}
                      >
                        {formatLabel(
                          equity.gate_status,
                        )}
                      </span>
                    </div>

                    <p className="equity-summary">
                      {equity.interpretation ??
                        equity.message}
                    </p>

                    {!equity
                      .auto_recommendation_eligible && (
                      <div className="recommendation-block">
                        <strong>
                          Automatic recommendation
                          blocked
                        </strong>

                        <p>
                          This location requires
                          enhanced community-impact,
                          public-health, and
                          environmental review.
                        </p>
                      </div>
                    )}

                    <div className="equity-facts">
                      <div>
                        <span>
                          Overburdened community
                        </span>

                        <strong>
                          {equity.overburdened
                            ? "Yes"
                            : "No"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Underserved community
                        </span>

                        <strong>
                          {equity.underserved
                            ? "Yes"
                            : "No"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Auto-recommendation
                        </span>

                        <strong>
                          {equity
                            .auto_recommendation_eligible
                            ? "Eligible"
                            : "Not eligible"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Census tract
                        </span>

                        <strong>
                          {equity.tract_geoid ??
                            "Unavailable"}
                        </strong>
                      </div>
                    </div>

                    <div className="percentile-grid">
                      <div>
                        <span>
                          Pollution burden
                        </span>

                        <strong>
                          {formatPercent(
                            equity.percentiles
                              ?.pollution_burden,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Environmental effects
                        </span>

                        <strong>
                          {formatPercent(
                            equity.percentiles
                              ?.environmental_effects,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Sensitive populations
                        </span>

                        <strong>
                          {formatPercent(
                            equity.percentiles
                              ?.sensitive_populations,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Overall EJ percentile
                        </span>

                        <strong>
                          {formatPercent(
                            equity.percentiles
                              ?.environmental_justice,
                          )}
                        </strong>
                      </div>
                    </div>

                    {equity.elevated_categories &&
                      equity.elevated_categories
                        .length > 0 && (
                        <div className="elevated-list">
                          <span>
                            Elevated indicators
                          </span>

                          <p>
                            {equity
                              .elevated_categories
                              .map(formatLabel)
                              .join(", ")}
                          </p>
                        </div>
                      )}

                    <details className="audit-details">
                      <summary>
                        Demographic audit fields
                      </summary>

                      <p>
                        These fields are used only
                        to audit disparate outcomes.
                        They never increase technical
                        suitability.
                      </p>

                      <div className="audit-grid">
                        <div>
                          <span>
                            Minority or Hispanic
                          </span>

                          <strong>
                            {formatPercent(
                              equity
                                .demographic_audit
                                ?.minority_or_hispanic_pct,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Low income
                          </span>

                          <strong>
                            {formatPercent(
                              equity
                                .demographic_audit
                                ?.low_income_pct,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Limited English
                          </span>

                          <strong>
                            {formatPercent(
                              equity
                                .demographic_audit
                                ?.limited_english_pct,
                            )}
                          </strong>
                        </div>
                      </div>
                    </details>
                  </section>
                )}

                <section className="criteria-section">
                  <div className="criteria-heading">
                    <div>
                      <p className="section-label">
                        Technical evidence
                      </p>

                      <h2>
                        Criterion scores
                      </h2>
                    </div>

                    <span>
                      {CRITERIA.length} variables
                    </span>
                  </div>

                  <div className="criteria-grid">
                    {CRITERIA.map(
                      (criterionName) => {
                        const criterion =
                          evaluation.criteria[
                            criterionName
                          ];

                        const score =
                          criterion
                            ?.normalized_score;

                        const numericScore =
                          typeof score === "number"
                            ? score
                            : null;

                        return (
                          <article
                            className="criterion-card"
                            key={criterionName}
                          >
                            <div className="criterion-header">
                              <h3>
                                {formatLabel(
                                  criterionName,
                                )}
                              </h3>

                              <span
                                className={
                                  criterion
                                    ?.excluded
                                    ? "criterion-state excluded"
                                    : "criterion-state"
                                }
                              >
                                {criterion
                                  ?.excluded
                                  ? "Excluded"
                                  : criterion
                                      ?.status ??
                                    "Unknown"}
                              </span>
                            </div>

                            <div className="criterion-score">
                              {formatScore(
                                numericScore,
                              )}
                            </div>

                            <div className="mini-track">
                              <div
                                style={{
                                  width:
                                    numericScore ===
                                    null
                                      ? "0%"
                                      : `${Math.round(
                                          numericScore *
                                            100,
                                        )}%`,
                                }}
                              />
                            </div>

                            <p>
                              {criterion
                                ?.source_layer ??
                                "Source unavailable"}
                            </p>
                          </article>
                        );
                      },
                    )}
                  </div>
                </section>
              </>
            )}
        </aside>
      </main>
    </div>
  );
}


export default App;
