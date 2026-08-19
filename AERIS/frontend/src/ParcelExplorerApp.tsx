import {
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  FeatureCollection,
  Geometry,
} from "geojson";

import * as maplibregl
  from "maplibre-gl";

import "maplibre-gl/dist/maplibre-gl.css";
import "./parcel.css";

import {
  fetchStatewideZones,
} from "./statewideApi";

import {
  fetchParcelDetail,
  fetchZoneParcels,
  type ParcelDetail,
  type ParcelFeatureCollection,
} from "./parcelApi";

import {
  ParcelDetails,
} from "./components/ParcelDetails";


const EMPTY_COLLECTION:
FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};


type ZoneOption = {
  zoneId: string;
  label: string;
};


function allCoordinates(
  geometry: Geometry,
): Array<[number, number]> {
  const coordinates: Array<
    [number, number]
  > = [];

  function visit(
    value: unknown,
  ): void {
    if (
      Array.isArray(value)
      && value.length >= 2
      && typeof value[0]
        === "number"
      && typeof value[1]
        === "number"
    ) {
      coordinates.push([
        value[0],
        value[1],
      ]);

      return;
    }

    if (Array.isArray(value)) {
      value.forEach(visit);
    }
  }

  if (
    "coordinates" in geometry
  ) {
    visit(geometry.coordinates);
  }

  return coordinates;
}


function collectionBounds(
  collection: FeatureCollection,
): maplibregl.LngLatBoundsLike | null {
  const coordinates = (
    collection.features.flatMap(
      (feature) =>
        feature.geometry
          ? allCoordinates(
              feature.geometry
            )
          : [],
    )
  );

  if (coordinates.length === 0) {
    return null;
  }

  const longitudes = coordinates.map(
    (coordinate) =>
      coordinate[0],
  );

  const latitudes = coordinates.map(
    (coordinate) =>
      coordinate[1],
  );

  return [
    [
      Math.min(...longitudes),
      Math.min(...latitudes),
    ],
    [
      Math.max(...longitudes),
      Math.max(...latitudes),
    ],
  ];
}


function sourceData(
  map: maplibregl.Map,
  sourceId: string,
  collection: FeatureCollection,
): void {
  const source = map.getSource(
    sourceId,
  ) as
    | maplibregl.GeoJSONSource
    | undefined;

  source?.setData(collection);
}


export default function ParcelExplorerApp() {
  const containerRef =
    useRef<HTMLDivElement | null>(
      null
    );

  const mapRef =
    useRef<maplibregl.Map | null>(
      null
    );

  const parcelScopeIdRef =
    useRef<string | null>(
      null
    );

  const [
    mapReady,
    setMapReady,
  ] = useState(false);

  const [
    zones,
    setZones,
  ] = useState<FeatureCollection>(
    EMPTY_COLLECTION,
  );

  const [
    zoneOptions,
    setZoneOptions,
  ] = useState<ZoneOption[]>([]);

  const [
    selectedZoneId,
    setSelectedZoneId,
  ] = useState("");

  const [
    parcels,
    setParcels,
  ] = useState<ParcelFeatureCollection | null>(
    null,
  );

  const [
    parcelDetail,
    setParcelDetail,
  ] = useState<ParcelDetail | null>(
    null,
  );

  const [
    loadingParcels,
    setLoadingParcels,
  ] = useState(false);

  const [
    loadingDetail,
    setLoadingDetail,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(
    null
  );


  useEffect(() => {
    parcelScopeIdRef.current = (
      parcels?.metadata
        .scope.scope_id
      ?? null
    );
  }, [parcels]);


  useEffect(() => {
    fetchStatewideZones("top")
      .then((result) => {
        setZones(result);

        const options =
          result.features
            .map((feature) => {
              const properties =
                feature.properties
                ?? {};

              const zoneId =
                properties["zone_id"];

              if (
                typeof zoneId
                !== "string"
              ) {
                return null;
              }

              const county =
                properties[
                  "dominant_county"
                ];

              return {
                zoneId,
                label:
                  `${zoneId} — `
                  + (
                    typeof county
                    === "string"
                      ? county
                      : "Maryland"
                  ),
              };
            })
            .filter(
              (
                option,
              ): option is ZoneOption =>
                option !== null,
            );

        setZoneOptions(options);

        if (options.length > 0) {
          setSelectedZoneId(
            options[0].zoneId
          );
        }
      })
      .catch((caughtError: unknown) => {
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : (
              "Candidate zones could "
              + "not be loaded."
            ),
        );
      });
  }, []);


  useEffect(() => {
    if (
      !containerRef.current
      || mapRef.current
    ) {
      return;
    }

    const map = new maplibregl.Map({
      container:
        containerRef.current,

      style:
        "https://tiles.openfreemap.org/"
        + "styles/liberty",

      center: [
        -76.7,
        39.0,
      ],

      zoom: 7,
    });

    mapRef.current = map;

    map.addControl(
      new maplibregl
        .NavigationControl(),
      "top-right",
    );

    map.on("load", () => {
      map.addSource(
        "parcel-zones",
        {
          type: "geojson",
          data: EMPTY_COLLECTION,
        },
      );

      map.addSource(
        "parcel-polygons",
        {
          type: "geojson",
          data: EMPTY_COLLECTION,
        },
      );

      map.addLayer({
        id: "parcel-zone-fill",
        type: "fill",
        source: "parcel-zones",
        paint: {
          "fill-color": "#7c3aed",
          "fill-opacity": 0.12,
        },
      });

      map.addLayer({
        id: "parcel-zone-line",
        type: "line",
        source: "parcel-zones",
        paint: {
          "line-color": "#6d28d9",
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            8,
            3,
            14,
            5,
          ],
        },
      });

      map.addLayer({
        id: "parcel-fill",
        type: "fill",
        source: "parcel-polygons",
        paint: {
          "fill-color": [
            "match",
            [
              "get",
              "availability_status",
            ],
            "PUBLIC_OR_INSTITUTIONAL",
            "#be123c",
            "EXISTING_USE_REVIEW_REQUIRED",
            "#d97706",
            "POTENTIAL_FURTHER_REVIEW",
            "#15803d",
            "DATA_INSUFFICIENT",
            "#64748b",
            "#64748b",
          ],
          "fill-opacity": [
            "interpolate",
            ["linear"],
            [
              "coalesce",
              [
                "get",
                "scope_overlap_fraction",
              ],
              0,
            ],
            0,
            0.05,
            0.05,
            0.10,
            0.25,
            0.20,
            0.50,
            0.30,
            1,
            0.42,
          ],
        },
      });

      map.addLayer({
        id: "parcel-line",
        type: "line",
        source: "parcel-polygons",
        paint: {
          "line-color": [
            "match",
            [
              "get",
              "availability_status",
            ],
            "PUBLIC_OR_INSTITUTIONAL",
            "#9f1239",
            "EXISTING_USE_REVIEW_REQUIRED",
            "#b45309",
            "POTENTIAL_FURTHER_REVIEW",
            "#166534",
            "#475569",
          ],
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            10,
            0.45,
            16,
            2.2,
          ],

          "line-opacity": [
            "interpolate",
            ["linear"],
            [
              "coalesce",
              [
                "get",
                "scope_overlap_fraction",
              ],
              0,
            ],
            0,
            0.10,
            0.05,
            0.20,
            0.25,
            0.55,
            0.50,
            0.78,
            1,
            1,
          ],
        },
      });

      map.moveLayer(
        "parcel-zone-fill"
      );

      map.moveLayer(
        "parcel-zone-line"
      );

      map.on(
        "mousemove",
        "parcel-fill",
        () => {
          map.getCanvas().style.cursor =
            "pointer";
        },
      );

      map.on(
        "mouseleave",
        "parcel-fill",
        () => {
          map.getCanvas().style.cursor =
            "";
        },
      );

      map.on(
        "click",
        "parcel-fill",
        (event) => {
          const feature =
            event.features?.[0];

          const parcelId =
            feature?.properties?.[
              "parcel_id"
            ];

          const scopeId =
            parcelScopeIdRef.current;

          if (
            typeof parcelId
              !== "string"
            || !scopeId
          ) {
            return;
          }

          setLoadingDetail(true);
          setError(null);

          fetchParcelDetail(
            scopeId,
            parcelId,
          )
            .then(
              setParcelDetail
            )
            .catch(
              (
                caughtError:
                  unknown,
              ) => {
                setError(
                  caughtError
                  instanceof Error
                    ? caughtError
                        .message
                    : (
                      "Parcel detail "
                      + "could not be "
                      + "loaded."
                    ),
                );
              },
            )
            .finally(() => {
              setLoadingDetail(
                false
              );
            });
        },
      );

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
      || !mapRef.current
    ) {
      return;
    }

    sourceData(
      mapRef.current,
      "parcel-zones",
      zones,
    );

    const selectedZoneFilter:
    maplibregl.FilterSpecification =
      selectedZoneId
        ? [
          "==",
          ["get", "zone_id"],
          selectedZoneId,
        ]
        : [
          "==",
          ["get", "zone_id"],
          "__NO_SELECTED_ZONE__",
        ];

    mapRef.current.setFilter(
      "parcel-zone-fill",
      selectedZoneFilter,
    );

    mapRef.current.setFilter(
      "parcel-zone-line",
      selectedZoneFilter,
    );
  }, [
    mapReady,
    zones,
    selectedZoneId,
  ]);


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    sourceData(
      mapRef.current,
      "parcel-polygons",
      parcels ?? EMPTY_COLLECTION,
    );

    if (parcels) {
      const bounds = collectionBounds(
        parcels
      );

      if (bounds) {
        mapRef.current.fitBounds(
          bounds,
          {
            padding: 50,
            duration: 600,
          },
        );
      }
    }
  }, [
    mapReady,
    parcels,
  ]);


  function loadSelectedZone(): void {
    if (!selectedZoneId) {
      return;
    }

    setLoadingParcels(true);
    setError(null);
    setParcelDetail(null);

    fetchZoneParcels(
      selectedZoneId
    )
      .then(setParcels)
      .catch(
        (
          caughtError:
            unknown,
        ) => {
          setError(
            caughtError
            instanceof Error
              ? caughtError.message
              : (
                "Parcel scope could "
                + "not be loaded."
              ),
          );
        },
      )
      .finally(() => {
        setLoadingParcels(false);
      });
  }


  return (
    <div className="parcel-app">
      <header className="parcel-topbar">
        <div>
          <span className="parcel-kicker">
            AERIS Maryland v0.3
          </span>

          <h1>
            Parcel Investigation
          </h1>
        </div>

        <div className="parcel-summary">
          <span>
            {
              parcels?.metadata
                .matching_count
                .toLocaleString()
              ?? "0"
            }
            {" "}
            parcels
          </span>

          <span>
            Availability unconfirmed
          </span>
        </div>
      </header>

      <main className="parcel-layout">
        <section className="parcel-map-panel">
          <div
            ref={containerRef}
            className="parcel-map"
          />

          <div className="parcel-legend">
            <div>
              <span className="parcel-swatch public" />
              Public or institutional
            </div>

            <div>
              <span className="parcel-swatch existing" />
              Existing-use review
            </div>

            <div>
              <span className="parcel-swatch potential" />
              Potential further review
            </div>

            <div>
              <span className="parcel-swatch unknown" />
              Insufficient data
            </div>
          </div>

          {loadingParcels && (
            <div className="parcel-loading">
              Acquiring and normalizing
              parcel geometry…
            </div>
          )}
        </section>

        <aside className="parcel-sidebar">
          {error && (
            <section className="parcel-error">
              <strong>
                Parcel explorer error
              </strong>

              <p>{error}</p>
            </section>
          )}

          <section className="parcel-control-card">
            <span className="parcel-kicker">
              Candidate-zone drill-down
            </span>

            <h2>
              Open parcel investigation
            </h2>

            <label>
              <span>Candidate zone</span>

              <select
                value={selectedZoneId}
                onChange={(event) => {
                  setSelectedZoneId(
                    event.target.value
                  );
                }}
              >
                {zoneOptions.map(
                  (option) => (
                    <option
                      key={
                        option.zoneId
                      }
                      value={
                        option.zoneId
                      }
                    >
                      {option.label}
                    </option>
                  ),
                )}
              </select>
            </label>

            <button
              type="button"
              disabled={
                loadingParcels
                || !selectedZoneId
              }
              onClick={
                loadSelectedZone
              }
            >
              {loadingParcels
                ? (
                  "Loading parcels…"
                )
                : (
                  "Load parcel outlines"
                )}
            </button>

            {parcels && (
              <div className="parcel-scope-note">
                <strong>
                  {
                    parcels.metadata
                      .returned_count
                      .toLocaleString()
                  }
                  {" "}
                  parcels rendered
                </strong>

                <p>
                  {parcels.metadata
                    .truncated
                    ? (
                      "The map response "
                      + "was limited for "
                      + "performance."
                    )
                    : (
                      "All matching "
                      + "parcels are "
                      + "displayed."
                    )}
                </p>
              </div>
            )}
          </section>

          <ParcelDetails
            parcel={parcelDetail}
            loading={loadingDetail}
          />
        </aside>
      </main>
    </div>
  );
}
