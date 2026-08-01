import {
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  FeatureCollection,
} from "geojson";

import * as maplibregl
  from "maplibre-gl";

import "maplibre-gl/dist/maplibre-gl.css";
import "./statewide.css";

import {
  fetchStatewideCell,
  fetchStatewideGrid,
  fetchStatewideSummary,
  fetchStatewideZone,
  fetchStatewideZones,
  type StatewideCellDetail,
  type StatewideFilterState,
  type StatewideSummary,
  type StatewideZoneDetail,
  type StatewideZoneMode,
} from "./statewideApi";

import {
  StatewideFilters,
} from "./components/StatewideFilters";

import {
  StatewideDetails,
} from "./components/StatewideDetails";


const EMPTY_COLLECTION: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};


const DEFAULT_FILTERS: StatewideFilterState = {
  scoreType: "technical",
  minimumScore: 0,
  maximumScore: 1,
  eligibility: "all",
  equityGate: "",
  county: "",
  excluded: "all",
};


function updateGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection,
): void {
  const source = map.getSource(
    sourceId,
  ) as maplibregl.GeoJSONSource | undefined;

  source?.setData(data);
}


export default function StatewideApp() {
  const containerRef =
    useRef<HTMLDivElement | null>(null);

  const mapRef =
    useRef<maplibregl.Map | null>(null);

  const [
    mapReady,
    setMapReady,
  ] = useState(false);

  const [
    summary,
    setSummary,
  ] = useState<StatewideSummary | null>(
    null,
  );

  const [
    filters,
    setFilters,
  ] = useState<StatewideFilterState>(
    DEFAULT_FILTERS,
  );

  const [
    appliedFilters,
    setAppliedFilters,
  ] = useState<StatewideFilterState>(
    DEFAULT_FILTERS,
  );

  const [
    zoneMode,
    setZoneMode,
  ] = useState<StatewideZoneMode>("top");

  const [
    showExcluded,
    setShowExcluded,
  ] = useState(true);

  const [
    gridData,
    setGridData,
  ] = useState<FeatureCollection>(
    EMPTY_COLLECTION,
  );

  const [
    zoneData,
    setZoneData,
  ] = useState<FeatureCollection>(
    EMPTY_COLLECTION,
  );

  const [
    selectedCell,
    setSelectedCell,
  ] = useState<StatewideCellDetail | null>(
    null,
  );

  const [
    selectedZone,
    setSelectedZone,
  ] = useState<StatewideZoneDetail | null>(
    null,
  );

  const [
    loadingMap,
    setLoadingMap,
  ] = useState(false);

  const [
    loadingDetail,
    setLoadingDetail,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  useEffect(() => {
    let active = true;

    fetchStatewideSummary()
      .then((result) => {
        if (active) {
          setSummary(result);
        }
      })
      .catch((caughtError: unknown) => {
        if (!active) {
          return;
        }

        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to load statewide summary.",
        );
      });

    return () => {
      active = false;
    };
  }, []);


  useEffect(() => {
    if (
      !containerRef.current
      || mapRef.current
    ) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style:
        "https://tiles.openfreemap.org/"
        + "styles/liberty",
      center: [-76.7, 39],
      zoom: 6.5,
    });

    mapRef.current = map;

    map.addControl(
      new maplibregl.NavigationControl(),
      "top-right",
    );

    map.on("load", () => {
      map.addSource(
        "statewide-grid",
        {
          type: "geojson",
          data: EMPTY_COLLECTION,
        },
      );

      map.addSource(
        "statewide-zones",
        {
          type: "geojson",
          data: EMPTY_COLLECTION,
        },
      );

      map.addLayer({
        id: "statewide-heatmap",
        type: "heatmap",
        source: "statewide-grid",
        maxzoom: 10,
        filter: [
          "==",
          ["get", "hard_excluded"],
          false,
        ],
        paint: {
          "heatmap-weight": [
            "interpolate",
            ["linear"],
            [
              "coalesce",
              ["get", "display_score"],
              0,
            ],
            0,
            0,
            1,
            1,
          ],
          "heatmap-intensity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            0.8,
            9,
            1.4,
          ],
          "heatmap-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            7,
            9,
            18,
          ],
          "heatmap-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6,
            0.84,
            10,
            0.15,
          ],
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(127,29,29,0)",
            0.15,
            "#7f1d1d",
            0.35,
            "#c2410c",
            0.5,
            "#d97706",
            0.68,
            "#ca8a04",
            0.82,
            "#65a30d",
            1,
            "#0f766e",
          ],
        },
      });

      map.addLayer({
        id: "statewide-points",
        type: "circle",
        source: "statewide-grid",
        minzoom: 8,
        filter: [
          "==",
          ["get", "hard_excluded"],
          false,
        ],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            8,
            2.5,
            11,
            7,
          ],
          "circle-color": [
            "interpolate",
            ["linear"],
            [
              "coalesce",
              ["get", "display_score"],
              0,
            ],
            0.2,
            "#7f1d1d",
            0.4,
            "#c2410c",
            0.6,
            "#d97706",
            0.7,
            "#ca8a04",
            0.8,
            "#65a30d",
            0.9,
            "#0f766e",
            1,
            "#064e3b",
          ],
          "circle-opacity": 0.8,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 0.4,
        },
      });

      map.addLayer({
        id: "statewide-excluded",
        type: "circle",
        source: "statewide-grid",
        filter: [
          "==",
          ["get", "hard_excluded"],
          true,
        ],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6,
            1.5,
            10,
            5,
          ],
          "circle-color": "#475569",
          "circle-opacity": 0.48,
          "circle-stroke-color": "#1e293b",
          "circle-stroke-width": 0.4,
        },
      });

      map.addLayer({
        id: "statewide-zones-fill",
        type: "fill",
        source: "statewide-zones",
        paint: {
          "fill-color": "#7c3aed",
          "fill-opacity": 0.2,
        },
      });

      map.addLayer({
        id: "statewide-zones-line",
        type: "line",
        source: "statewide-zones",
        paint: {
          "line-color": "#6d28d9",
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            1.5,
            10,
            4,
          ],
          "line-opacity": 0.95,
        },
      });

      map.on("mousemove", (event) => {
        const features =
          map.queryRenderedFeatures(
            event.point,
            {
              layers: [
                "statewide-zones-fill",
                "statewide-points",
                "statewide-excluded",
              ],
            },
          );

        map.getCanvas().style.cursor =
          features.length > 0
            ? "pointer"
            : "";
      });

      map.on("click", (event) => {
        const features =
          map.queryRenderedFeatures(
            event.point,
            {
              layers: [
                "statewide-zones-fill",
                "statewide-points",
                "statewide-excluded",
              ],
            },
          );

        const zoneFeature =
          features.find(
            (feature) =>
              feature.layer.id
              === "statewide-zones-fill",
          );

        const zoneId =
          zoneFeature?.properties?.zone_id;

        if (typeof zoneId === "string") {
          setLoadingDetail(true);
          setError(null);

          fetchStatewideZone(zoneId)
            .then((result) => {
              setSelectedZone(result);
              setSelectedCell(null);
            })
            .catch(
              (caughtError: unknown) => {
                setError(
                  caughtError instanceof Error
                    ? caughtError.message
                    : "Unable to load zone detail.",
                );
              },
            )
            .finally(() => {
              setLoadingDetail(false);
            });

          return;
        }

        const cellFeature =
          features.find(
            (feature) =>
              feature.layer.id
              === "statewide-points"
              || feature.layer.id
              === "statewide-excluded",
          );

        const cellId =
          cellFeature?.properties?.cell_id;

        if (typeof cellId !== "string") {
          return;
        }

        setLoadingDetail(true);
        setError(null);

        fetchStatewideCell(cellId)
          .then((result) => {
            setSelectedCell(result);
            setSelectedZone(null);
          })
          .catch(
            (caughtError: unknown) => {
              setError(
                caughtError instanceof Error
                  ? caughtError.message
                  : "Unable to load cell detail.",
              );
            },
          )
          .finally(() => {
            setLoadingDetail(false);
          });
      });

      setMapReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);


  useEffect(() => {
    if (
      !mapReady
      || !summary
      || !mapRef.current
    ) {
      return;
    }

    mapRef.current.fitBounds(
      [
        [
          summary.bounds.west,
          summary.bounds.south,
        ],
        [
          summary.bounds.east,
          summary.bounds.north,
        ],
      ],
      {
        padding: 45,
        duration: 0,
      },
    );
  }, [
    mapReady,
    summary,
  ]);


  useEffect(() => {
    let active = true;

    setLoadingMap(true);
    setError(null);

    fetchStatewideGrid(
      appliedFilters,
    )
      .then((result) => {
        if (active) {
          setGridData(result);
        }
      })
      .catch((caughtError: unknown) => {
        if (!active) {
          return;
        }

        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to load statewide grid.",
        );
      })
      .finally(() => {
        if (active) {
          setLoadingMap(false);
        }
      });

    return () => {
      active = false;
    };
  }, [appliedFilters]);


  useEffect(() => {
    let active = true;

    fetchStatewideZones(zoneMode)
      .then((result) => {
        if (active) {
          setZoneData(result);
        }
      })
      .catch((caughtError: unknown) => {
        if (!active) {
          return;
        }

        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to load candidate zones.",
        );
      });

    return () => {
      active = false;
    };
  }, [zoneMode]);


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    updateGeoJsonSource(
      mapRef.current,
      "statewide-grid",
      gridData,
    );
  }, [
    gridData,
    mapReady,
  ]);


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    updateGeoJsonSource(
      mapRef.current,
      "statewide-zones",
      zoneData,
    );
  }, [
    zoneData,
    mapReady,
  ]);


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    mapRef.current.setLayoutProperty(
      "statewide-excluded",
      "visibility",
      showExcluded
        ? "visible"
        : "none",
    );
  }, [
    mapReady,
    showExcluded,
  ]);


  function resetFilters(): void {
    setFilters({
      ...DEFAULT_FILTERS,
    });

    setAppliedFilters({
      ...DEFAULT_FILTERS,
    });

    setZoneMode("top");
    setShowExcluded(true);
  }


  return (
    <div className="statewide-app">
      <header className="statewide-topbar">
        <div>
          <span className="statewide-kicker">
            AERIS Maryland v0.2
          </span>

          <h1>
            Statewide Screening Explorer
          </h1>
        </div>

        <div className="statewide-topbar-stats">
          <span>
            {gridData.features.length
              .toLocaleString()}
            {" "}
            heatmap cells
          </span>

          <span>
            {zoneData.features.length
              .toLocaleString()}
            {" "}
            candidate zones
          </span>

          <span
            className={
              summary?.audit.status
              === "PASS"
                ? "audit-pass"
                : "audit-review"
            }
          >
            Audit {
              summary?.audit.status
              ?? "loading"
            }
          </span>
        </div>
      </header>

      <main className="statewide-layout">
        <section className="statewide-map-panel">
          <div
            ref={containerRef}
            className="statewide-map"
          />

          <div className="statewide-map-title">
            <strong>
              {
                appliedFilters.scoreType
                === "technical"
                  ? "Technical suitability"
                  : "Effective suitability"
              }
            </strong>

            <span>
              {appliedFilters.minimumScore
                .toFixed(2)}
              {" – "}
              {appliedFilters.maximumScore
                .toFixed(2)}
            </span>
          </div>

          <div className="statewide-zone-legend">
            <span className="zone-swatch" />

            <span>
              Regional screening candidate zones
            </span>
          </div>

          <div className="statewide-legend">
            <span>Lower</span>
            <div className="statewide-gradient" />
            <span>Higher</span>
          </div>

          {loadingMap && (
            <div className="statewide-map-loading">
              Updating statewide heatmap…
            </div>
          )}
        </section>

        <aside className="statewide-sidebar">
          {error && (
            <section className="statewide-error-card">
              <strong>
                Statewide explorer error
              </strong>

              <p>{error}</p>
            </section>
          )}

          <StatewideFilters
            summary={summary}
            filters={filters}
            zoneMode={zoneMode}
            showExcluded={showExcluded}
            loading={loadingMap}
            onFiltersChange={setFilters}
            onZoneModeChange={setZoneMode}
            onShowExcludedChange={
              setShowExcluded
            }
            onApply={() => {
              setAppliedFilters({
                ...filters,
              });
            }}
            onReset={resetFilters}
          />

          <StatewideDetails
            summary={summary}
            cell={selectedCell}
            zone={selectedZone}
            loading={loadingDetail}
          />
        </aside>
      </main>
    </div>
  );
}
