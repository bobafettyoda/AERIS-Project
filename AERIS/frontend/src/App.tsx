import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  Geometry,
} from "geojson";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  API_BASE_URL,
  evaluateCandidateSite,
  evaluateEquityScreen,
  fetchMarylandBoundary,
  fetchSiteMapEvidence,
  type CandidatePoint,
  type EquityScreenResult,
  type SiteEvaluation,
  type SiteMapEvidence,
} from "./api";

import {
  loadSavedCandidates,
  nextCandidateLabel,
  storeSavedCandidates,
  type SavedCandidate,
} from "./candidates";

import {
  addEvidenceLayers,
  applyEvidenceVisibility,
  DEFAULT_VISIBILITY,
  updateEvidenceSources,
  type EvidenceGroup,
  type EvidenceVisibility,
} from "./mapEvidence";

import {
  ComparisonPanel,
} from "./components/ComparisonPanel";

import {
  CriterionCard,
} from "./components/CriterionCard";

import {
  LayerControl,
} from "./components/LayerControl";

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


const CRITERION_LAYER_GROUP:
Partial<Record<string, EvidenceGroup>> = {
  grid_infrastructure: "grid",
  protected_areas: "protected",
  water_bodies: "water",
  road_access: "roads",
  hydro_hazard: "flood",
};


function formatLabel(
  value: string,
): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() +
        word.slice(1),
    )
    .join(" ");
}


function formatPercent(
  value: number | null | undefined,
): string {
  if (
    value === null ||
    value === undefined
  ) {
    return "Not available";
  }

  return `${Math.round(value)}%`;
}


function extendCoordinateBounds(
  bounds:
    maplibregl.LngLatBounds,
  coordinates: unknown,
): void {
  if (!Array.isArray(coordinates)) {
    return;
  }

  if (
    coordinates.length >= 2 &&
    typeof coordinates[0] ===
      "number" &&
    typeof coordinates[1] ===
      "number"
  ) {
    bounds.extend([
      coordinates[0],
      coordinates[1],
    ]);

    return;
  }

  for (
    const coordinate
    of coordinates
  ) {
    extendCoordinateBounds(
      bounds,
      coordinate,
    );
  }
}


function extendGeometryBounds(
  bounds:
    maplibregl.LngLatBounds,
  geometry: Geometry,
): void {
  if (
    geometry.type ===
    "GeometryCollection"
  ) {
    for (
      const child
      of geometry.geometries
    ) {
      extendGeometryBounds(
        bounds,
        child,
      );
    }

    return;
  }

  extendCoordinateBounds(
    bounds,
    geometry.coordinates,
  );
}


function equityBadgeClass(
  status:
    EquityScreenResult[
      "gate_status"
    ],
): string {
  switch (status) {
    case "PASS":
      return "equity-badge pass";

    case "CAUTION":
      return "equity-badge caution";

    case "HIGH_BURDEN":
      return (
        "equity-badge high-burden"
      );

    default:
      return (
        "equity-badge insufficient"
      );
  }
}


function App() {
  const mapContainerRef =
    useRef<HTMLDivElement | null>(
      null
    );

  const mapRef =
    useRef<maplibregl.Map | null>(
      null
    );

  const markerRef =
    useRef<maplibregl.Marker | null>(
      null
    );

  const savedMarkersRef =
    useRef<
      Map<string, maplibregl.Marker>
    >(
      new Map()
    );

  const requestRef =
    useRef<AbortController | null>(
      null
    );

  const evidenceRequestRef =
    useRef<AbortController | null>(
      null
    );

  const boundaryRequestRef =
    useRef<AbortController | null>(
      null
    );

  const [
    selectedPoint,
    setSelectedPoint,
  ] = useState<CandidatePoint>(
    INITIAL_POINT
  );

  const [
    evaluation,
    setEvaluation,
  ] = useState<
    SiteEvaluation | null
  >(null);

  const [
    equity,
    setEquity,
  ] = useState<
    EquityScreenResult | null
  >(null);

  const [
    mapEvidence,
    setMapEvidence,
  ] = useState<
    SiteMapEvidence | null
  >(null);

  const [
    savedCandidates,
    setSavedCandidates,
  ] = useState<SavedCandidate[]>(
    () => loadSavedCandidates()
  );

  const [
    visibility,
    setVisibility,
  ] = useState<EvidenceVisibility>(
    DEFAULT_VISIBILITY
  );

  const [
    mapReady,
    setMapReady,
  ] = useState(false);

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    evidenceLoading,
    setEvidenceLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(
    null
  );

  const [
    equityError,
    setEquityError,
  ] = useState<string | null>(
    null
  );

  const [
    evidenceError,
    setEvidenceError,
  ] = useState<string | null>(
    null
  );


  useEffect(() => {
    storeSavedCandidates(
      savedCandidates
    );
  }, [savedCandidates]);


  const placeMarker = useCallback(
    (
      point: CandidatePoint
    ) => {
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


  const loadEvidenceOnly =
    useCallback(
      async (
        point: CandidatePoint
      ) => {
        evidenceRequestRef.current
          ?.abort();

        const controller =
          new AbortController();

        evidenceRequestRef.current =
          controller;

        setEvidenceLoading(true);
        setEvidenceError(null);

        try {
          const result =
            await fetchSiteMapEvidence(
              point,
              controller.signal,
            );

          setMapEvidence(result);
        } catch (caughtError) {
          if (
            caughtError instanceof
              DOMException &&
            caughtError.name ===
              "AbortError"
          ) {
            return;
          }

          setMapEvidence(null);

          setEvidenceError(
            caughtError instanceof Error
              ? caughtError.message
              : "Map evidence failed."
          );
        } finally {
          if (
            evidenceRequestRef.current ===
            controller
          ) {
            evidenceRequestRef.current =
              null;

            setEvidenceLoading(false);
          }
        }
      },
      [],
    );


  const evaluatePoint = useCallback(
    async (
      point: CandidatePoint
    ) => {
      requestRef.current?.abort();
      evidenceRequestRef.current
        ?.abort();

      const controller =
        new AbortController();

      requestRef.current =
        controller;

      setSelectedPoint(point);
      setLoading(true);
      setError(null);
      setEquityError(null);
      setEvidenceError(null);
      setEquity(null);
      setMapEvidence(null);

      try {
        const technicalResult =
          await evaluateCandidateSite(
            point,
            controller.signal,
          );

        setEvaluation(
          technicalResult
        );

        if (
          technicalResult.decision
            .status ===
            "outside_study_area" ||
          technicalResult.study_area
            ?.inside_study_area ===
            false
        ) {
          return;
        }

        const [
          equityResult,
          evidenceResult,
        ] = await Promise.allSettled([
          evaluateEquityScreen(
            point,
            controller.signal,
          ),
          fetchSiteMapEvidence(
            point,
            controller.signal,
          ),
        ]);

        if (
          equityResult.status ===
          "fulfilled"
        ) {
          setEquity(
            equityResult.value
          );
        } else {
          setEquityError(
            equityResult.reason
              instanceof Error
              ? equityResult.reason
                  .message
              : "Equity screen failed."
          );
        }

        if (
          evidenceResult.status ===
          "fulfilled"
        ) {
          setMapEvidence(
            evidenceResult.value
          );
        } else {
          setEvidenceError(
            evidenceResult.reason
              instanceof Error
              ? evidenceResult.reason
                  .message
              : "Map evidence failed."
          );
        }
      } catch (caughtError) {
        if (
          caughtError instanceof
            DOMException &&
          caughtError.name ===
            "AbortError"
        ) {
          return;
        }

        setEvaluation(null);
        setEquity(null);
        setMapEvidence(null);

        setError(
          caughtError instanceof Error
            ? caughtError.message
            : (
              "Candidate-site " +
              "evaluation failed."
            )
        );
      } finally {
        if (
          requestRef.current ===
          controller
        ) {
          requestRef.current =
            null;

          setLoading(false);
        }
      }
    },
    [],
  );


  const showSavedCandidate =
    useCallback(
      (
        candidate:
          SavedCandidate
      ) => {
        setSelectedPoint(
          candidate.point
        );

        setEvaluation(
          candidate.evaluation
        );

        setEquity(
          candidate.equity
        );

        setError(null);
        setEquityError(null);

        placeMarker(
          candidate.point
        );

        mapRef.current?.flyTo({
          center: [
            candidate.point.lon,
            candidate.point.lat,
          ],
          zoom: 12.5,
          essential: true,
        });

        void loadEvidenceOnly(
          candidate.point
        );
      },
      [
        loadEvidenceOnly,
        placeMarker,
      ],
    );


  useEffect(() => {
    for (
      const marker
      of savedMarkersRef.current
        .values()
    ) {
      marker.remove();
    }

    savedMarkersRef.current.clear();

    const map = mapRef.current;

    if (!mapReady || !map) {
      return;
    }

    for (
      const candidate
      of savedCandidates
    ) {
      const element =
        document.createElement(
          "button"
        );

      element.type = "button";
      element.className =
        "saved-candidate-marker";
      element.textContent =
        candidate.label;
      element.title =
        candidate.name;

      element.addEventListener(
        "click",
        (event) => {
          event.stopPropagation();

          showSavedCandidate(
            candidate
          );
        },
      );

      const marker =
        new maplibregl.Marker({
          element,
          anchor: "center",
        })
          .setLngLat([
            candidate.point.lon,
            candidate.point.lat,
          ])
          .addTo(map);

      savedMarkersRef.current.set(
        candidate.id,
        marker
      );
    }
  }, [
    mapReady,
    savedCandidates,
    showSavedCandidate,
  ]);


  useEffect(() => {
    const map = mapRef.current;

    if (
      !mapReady ||
      !map
    ) {
      return;
    }

    updateEvidenceSources(
      map,
      mapEvidence
    );
  }, [
    mapEvidence,
    mapReady,
  ]);


  useEffect(() => {
    const map = mapRef.current;

    if (
      !mapReady ||
      !map
    ) {
      return;
    }

    applyEvidenceVisibility(
      map,
      visibility
    );
  }, [
    mapReady,
    visibility,
  ]);


  useEffect(() => {
    if (
      !mapContainerRef.current ||
      mapRef.current
    ) {
      return;
    }

    const map =
      new maplibregl.Map({
        container:
          mapContainerRef.current,

        style:
          "https://tiles.openfreemap.org/" +
          "styles/liberty",

        center: [
          INITIAL_POINT.lon,
          INITIAL_POINT.lat,
        ],

        zoom: 8,
      });

    mapRef.current = map;

    map.addControl(
      new maplibregl
        .NavigationControl(),
      "top-right",
    );

    const boundaryController =
      new AbortController();

    boundaryRequestRef.current =
      boundaryController;

    map.on(
      "load",
      async () => {
        addEvidenceLayers(map);

        applyEvidenceVisibility(
          map,
          visibility
        );

        placeMarker(
          INITIAL_POINT
        );

        setMapReady(true);

        try {
          const boundary =
            await fetchMarylandBoundary(
              boundaryController
                .signal,
            );

          map.addSource(
            "maryland-boundary",
            {
              type: "geojson",
              data: boundary,
            },
          );

          map.addLayer({
            id:
              "maryland-boundary-fill",
            type: "fill",
            source:
              "maryland-boundary",
            paint: {
              "fill-color":
                "#147d7f",
              "fill-opacity": 0.035,
            },
          });

          map.addLayer({
            id:
              "maryland-boundary-line",
            type: "line",
            source:
              "maryland-boundary",
            paint: {
              "line-color":
                "#d97706",
              "line-width": 3,
              "line-opacity": 0.95,
            },
          });

          const bounds =
            new maplibregl
              .LngLatBounds();

          for (
            const feature
            of boundary.features
          ) {
            if (feature.geometry) {
              extendGeometryBounds(
                bounds,
                feature.geometry,
              );
            }
          }

          if (!bounds.isEmpty()) {
            map.fitBounds(
              bounds,
              {
                padding: 42,
                duration: 0,
              },
            );
          }
        } catch (
          boundaryError
        ) {
          if (
            boundaryError
              instanceof
                DOMException &&
            boundaryError.name ===
              "AbortError"
          ) {
            return;
          }

          console.error(
            "Maryland boundary " +
            "failed to load:",
            boundaryError,
          );
        }
      },
    );

    map.on(
      "click",
      (
        event:
          maplibregl
            .MapMouseEvent
      ) => {
        const point:
        CandidatePoint = {
          lat: Number(
            event.lngLat.lat
              .toFixed(6),
          ),

          lon: Number(
            event.lngLat.lng
              .toFixed(6),
          ),
        };

        placeMarker(point);

        void evaluatePoint(
          point
        );
      },
    );

    return () => {
      requestRef.current
        ?.abort();

      evidenceRequestRef.current
        ?.abort();

      boundaryRequestRef.current
        ?.abort();

      for (
        const marker
        of savedMarkersRef.current
          .values()
      ) {
        marker.remove();
      }

      savedMarkersRef.current
        .clear();

      markerRef.current?.remove();
      markerRef.current = null;

      map.remove();
      mapRef.current = null;
    };
  }, [
    evaluatePoint,
    placeMarker,
  ]);


  const saveCurrentCandidate =
    useCallback(() => {
      if (
        !evaluation ||
        evaluation.decision
          .status ===
          "outside_study_area"
      ) {
        return;
      }

      const duplicate =
        savedCandidates.some(
          (candidate) =>
            Math.abs(
              candidate.point.lat -
              selectedPoint.lat
            ) < 0.000001 &&
            Math.abs(
              candidate.point.lon -
              selectedPoint.lon
            ) < 0.000001
        );

      if (
        duplicate ||
        savedCandidates.length >= 5
      ) {
        return;
      }

      const label =
        nextCandidateLabel(
          savedCandidates
        );

      const id =
        typeof crypto
          .randomUUID ===
          "function"
          ? crypto.randomUUID()
          : (
            `${Date.now()}-` +
            label
          );

      const candidate:
      SavedCandidate = {
        id,
        label,
        name:
          `Candidate ${label}`,
        point: selectedPoint,
        evaluation,
        equity,
        savedAt:
          new Date()
            .toISOString(),
      };

      setSavedCandidates(
        (current) => [
          ...current,
          candidate,
        ]
      );
    }, [
      equity,
      evaluation,
      savedCandidates,
      selectedPoint,
    ]);


  const removeCandidate =
    useCallback(
      (
        candidateId: string
      ) => {
        setSavedCandidates(
          (current) =>
            current.filter(
              (candidate) =>
                candidate.id !==
                candidateId
            )
        );
      },
      [],
    );


  const clearCandidates =
    useCallback(() => {
      setSavedCandidates([]);
    }, []);


  const updateLayerVisibility =
    useCallback(
      (
        group: EvidenceGroup,
        visible: boolean,
      ) => {
        setVisibility(
          (current) => ({
            ...current,
            [group]: visible,
          })
        );
      },
      [],
    );


  const showCriterionEvidence =
    useCallback(
      (
        criterionName: string
      ) => {
        const group =
          CRITERION_LAYER_GROUP[
            criterionName
          ];

        if (group) {
          setVisibility(
            (current) => ({
              ...current,
              [group]: true,
            })
          );
        }

        mapRef.current?.flyTo({
          center: [
            selectedPoint.lon,
            selectedPoint.lat,
          ],
          zoom: 13,
          essential: true,
        });
      },
      [selectedPoint],
    );


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
          suitabilityScore *
            100
        );

  const outsideStudyArea =
    evaluation?.decision
      .status ===
    "outside_study_area";

  const alreadySaved =
    savedCandidates.some(
      (candidate) =>
        Math.abs(
          candidate.point.lat -
          selectedPoint.lat
        ) < 0.000001 &&
        Math.abs(
          candidate.point.lon -
          selectedPoint.lon
        ) < 0.000001
    );

  const canSave =
    Boolean(evaluation) &&
    !outsideStudyArea &&
    !alreadySaved &&
    savedCandidates.length < 5;


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">
            Maryland Data Center
            Siting Screening Tool
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

          <LayerControl
            visibility={visibility}
            onChange={
              updateLayerVisibility
            }
          />

          <div className="map-message">
            Click inside Maryland to
            evaluate a candidate location.
          </div>

          {evidenceLoading && (
            <div className="map-loading-chip">
              Loading map evidence…
            </div>
          )}
        </section>

        <aside className="results-panel">
          <section className="location-card">
            <div>
              <p className="section-label">
                Selected location
              </p>

              <strong>
                {selectedPoint.lat
                  .toFixed(5)}
                ,{" "}
                {selectedPoint.lon
                  .toFixed(5)}
              </strong>

              <small className="saved-count">
                {
                  savedCandidates.length
                }
                /5 candidates saved
              </small>
            </div>

            <div className="location-actions">
              <button
                type="button"
                disabled={loading}
                onClick={() => {
                  placeMarker(
                    selectedPoint
                  );

                  void evaluatePoint(
                    selectedPoint
                  );
                }}
              >
                {loading
                  ? "Evaluating..."
                  : "Evaluate site"}
              </button>

              <button
                type="button"
                className="secondary-button"
                disabled={!canSave}
                onClick={
                  saveCurrentCandidate
                }
              >
                {alreadySaved
                  ? "Candidate saved"
                  : savedCandidates
                      .length >= 5
                    ? "Maximum saved"
                    : "Save candidate"}
              </button>
            </div>
          </section>

          {loading && (
            <section className="notice">
              <span className="spinner" />

              <div>
                <strong>
                  Running Maryland analysis
                </strong>

                <p>
                  Evaluating technical
                  criteria, equity safeguards,
                  and nearby GIS evidence.
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

          {evidenceError && (
            <section className="notice warning">
              <div>
                <strong>
                  Map evidence incomplete
                </strong>

                <p>
                  {evidenceError}
                </p>
              </div>
            </section>
          )}

          {!loading &&
            !error &&
            !evaluation && (
              <section className="empty-state">
                <h2>
                  Evaluate a Maryland site
                </h2>

                <p>
                  Click the map or evaluate
                  the selected location.
                </p>
              </section>
            )}

          {!loading &&
            evaluation &&
            outsideStudyArea && (
              <section className="notice error">
                <div>
                  <strong>
                    Outside the Maryland
                    study area
                  </strong>

                  <p>
                    {
                      evaluation.decision
                        .message
                    }
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
                        ? (
                          "decision-badge " +
                          "excluded"
                        )
                        : (
                          "decision-badge " +
                          "complete"
                        )
                    }
                  >
                    {evaluation.decision
                      .hard_excluded
                      ? "Excluded"
                      : evaluation.decision
                          .status}
                  </span>

                  <div className="score-track">
                    <div
                      className="score-fill"
                      style={{
                        width:
                          `${
                            scorePercent ??
                            0
                          }%`,
                      }}
                    />
                  </div>

                  <p className="score-caption">
                    Technical model completion:
                    {" "}
                    {
                      evaluation.score_summary
                        .model_completion_percent
                    }
                    %. Community burden is
                    evaluated separately.
                  </p>
                </section>

                {equityError && (
                  <section className="notice error">
                    <div>
                      <strong>
                        Community-impact
                        data unavailable
                      </strong>

                      <p>
                        {equityError}
                      </p>
                    </div>
                  </section>
                )}

                {equity && (
                  <section className="equity-card">
                    <div className="equity-heading">
                      <div>
                        <p className="section-label">
                          Community impact
                          and equity
                        </p>

                        <h2>
                          Environmental-
                          justice gate
                        </h2>
                      </div>

                      <span
                        className={
                          equityBadgeClass(
                            equity
                              .gate_status
                          )
                        }
                      >
                        {formatLabel(
                          equity
                            .gate_status
                        )}
                      </span>
                    </div>

                    <p className="equity-summary">
                      {equity
                        .interpretation ??
                        equity.message}
                    </p>

                    {!equity
                      .auto_recommendation_eligible && (
                      <div className="recommendation-block">
                        <strong>
                          Automatic
                          recommendation blocked
                        </strong>

                        <p>
                          Enhanced community-
                          impact, public-health,
                          and environmental review
                          is required.
                        </p>
                      </div>
                    )}

                    <div className="equity-facts">
                      <div>
                        <span>
                          Overburdened community
                        </span>

                        <strong>
                          {equity
                            .overburdened
                            ? "Yes"
                            : "No"}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Underserved community
                        </span>

                        <strong>
                          {equity
                            .underserved
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
                          {
                            equity
                              .tract_geoid ??
                            "Unavailable"
                          }
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
                            equity
                              .percentiles
                              ?.pollution_burden
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Environmental effects
                        </span>

                        <strong>
                          {formatPercent(
                            equity
                              .percentiles
                              ?.environmental_effects
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Sensitive populations
                        </span>

                        <strong>
                          {formatPercent(
                            equity
                              .percentiles
                              ?.sensitive_populations
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          Overall EJ percentile
                        </span>

                        <strong>
                          {formatPercent(
                            equity
                              .percentiles
                              ?.environmental_justice
                          )}
                        </strong>
                      </div>
                    </div>

                    <details className="audit-details">
                      <summary>
                        Demographic audit fields
                      </summary>

                      <p>
                        These fields audit
                        disparate outcomes. They
                        never increase technical
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
                                ?.minority_or_hispanic_pct
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
                                ?.low_income_pct
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
                                ?.limited_english_pct
                            )}
                          </strong>
                        </div>
                      </div>
                    </details>
                  </section>
                )}

                <ComparisonPanel
                  candidates={
                    savedCandidates
                  }
                  onSelect={
                    showSavedCandidate
                  }
                  onRemove={
                    removeCandidate
                  }
                  onClear={
                    clearCandidates
                  }
                />

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
                      {CRITERIA.length}
                      {" "}
                      variables
                    </span>
                  </div>

                  <div className="criteria-grid">
                    {CRITERIA.map(
                      (
                        criterionName
                      ) => (
                        <CriterionCard
                          key={
                            criterionName
                          }
                          criterionName={
                            criterionName
                          }
                          criterion={
                            evaluation
                              .criteria[
                                criterionName
                              ]
                          }
                          canShowOnMap={
                            criterionName in
                            CRITERION_LAYER_GROUP
                          }
                          onShowOnMap={() => {
                            showCriterionEvidence(
                              criterionName
                            );
                          }}
                        />
                      ),
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
