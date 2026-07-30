import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  API_BASE_URL,
  evaluateCandidateSite,
  type CandidatePoint,
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


function App() {
  const mapContainerRef =
    useRef<HTMLDivElement | null>(null);

  const mapRef =
    useRef<maplibregl.Map | null>(null);

  const markerRef =
    useRef<maplibregl.Marker | null>(null);

  const requestRef =
    useRef<AbortController | null>(null);

  const [selectedPoint, setSelectedPoint] =
    useState<CandidatePoint>(INITIAL_POINT);

  const [evaluation, setEvaluation] =
    useState<SiteEvaluation | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
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
            .setLngLat([point.lon, point.lat])
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

      try {
        const result = await evaluateCandidateSite(
          point,
          controller.signal,
        );

        setEvaluation(result);
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
      zoom: 11,
    });

    mapRef.current = map;

    map.addControl(
      new maplibregl.NavigationControl(),
      "top-right",
    );

    map.on("load", () => {
      placeMarker(INITIAL_POINT);
    });

    map.on("click", (event: maplibregl.MapMouseEvent) => {
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
    });

    return () => {
      requestRef.current?.abort();
      markerRef.current?.remove();

      markerRef.current = null;
      mapRef.current = null;

      map.remove();
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
      : Math.round(suitabilityScore * 100);


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">
            Assessment of Environmental Risk
            and Incident Siting
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

          <div className="map-message">
            Click the map to evaluate a candidate
            location.
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
                void evaluatePoint(selectedPoint);
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
                  Running AERIS analysis
                </strong>

                <p>
                  Evaluating all eight siting
                  criteria.
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
                  another location on the map.
                </p>
              </section>
            )}

          {evaluation && !loading && (
            <>
              <section className="score-card">
                <div>
                  <p className="section-label">
                    Final suitability
                  </p>

                  <div className="score-number">
                    {scorePercent ?? "—"}
                    <span>/100</span>
                  </div>
                </div>

                <span
                  className={
                    evaluation.decision.hard_excluded
                      ? "decision-badge excluded"
                      : "decision-badge complete"
                  }
                >
                  {evaluation.decision.hard_excluded
                    ? "Excluded"
                    : evaluation.decision.status}
                </span>

                <div className="score-track">
                  <div
                    className="score-fill"
                    style={{
                      width: `${scorePercent ?? 0}%`,
                    }}
                  />
                </div>

                <p className="score-caption">
                  Model completion:{" "}
                  {
                    evaluation.score_summary
                      .model_completion_percent
                  }
                  %
                </p>
              </section>

              {evaluation.decision
                .hard_excluded && (
                <section className="notice error">
                  <div>
                    <strong>
                      Hard exclusion triggered
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

              <section className="criteria-section">
                <div className="criteria-heading">
                  <div>
                    <p className="section-label">
                      Model evidence
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
                                criterion?.excluded
                                  ? "criterion-state excluded"
                                  : "criterion-state"
                              }
                            >
                              {criterion?.excluded
                                ? "Excluded"
                                : criterion?.status ??
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
                                  numericScore === null
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
