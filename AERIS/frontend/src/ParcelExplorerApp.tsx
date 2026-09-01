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

import { AERIS_RELEASE_LABEL } from "./generated/release";

import {
  fetchStatewideZones,
} from "./statewideApi";

import {
  fetchParcelDetail,
  type ParcelDetail,
} from "./parcelApi";

import {
  useParcelScope,
} from "./parcel/useParcelScope";

import {
  applyParcelView,
  type ParcelView,
} from "./parcel/viewLayers";

import {
  addParcelMapLayers,
} from "./parcel/mapSetup";

import {
  ParcelDetails,
} from "./components/ParcelDetails";

import {
  ParcelControls,
  type ZoneOption,
} from "./components/ParcelControls";

import {
  SiteCandidateComparison,
} from "./components/SiteCandidateComparison";


const EMPTY_COLLECTION:
FeatureCollection = {
  type: "FeatureCollection",
  features: [],
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
    parcelDetail,
    setParcelDetail,
  ] = useState<ParcelDetail | null>(
    null,
  );

  const [
    parcelView,
    setParcelView,
  ] = useState<ParcelView>(
    "parcels"
  );

  const [
    detailError,
    setDetailError,
  ] = useState<string | null>(
    null
  );

  const [
    loadingDetail,
    setLoadingDetail,
  ] = useState(false);

  const {
    parcels,
    envelopes,
    constraints,
    gridEvidence,
    planningEvidence,
    siteEvidence,
    artifacts,
    job,
    loading: loadingParcels,
    error: scopeError,
    loadZone,
  } = useParcelScope();


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
        setDetailError(
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
      addParcelMapLayers(
        map,
        EMPTY_COLLECTION,
      );

      const pointerLayers = [
        "parcel-fill",
        "parcel-site-envelope-fill",
      ];

      const openParcel = (
        event: maplibregl.MapLayerMouseEvent,
      ) => {
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
        setDetailError(null);

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
              setDetailError(
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
      };

      for (const layerId of pointerLayers) {
        map.on(
          "mousemove",
          layerId,
          () => {
            map.getCanvas().style.cursor =
              "pointer";
          },
        );

        map.on(
          "mouseleave",
          layerId,
          () => {
            map.getCanvas().style.cursor =
              "";
          },
        );

        map.on(
          "click",
          layerId,
          openParcel,
        );
      }

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


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    sourceData(
      mapRef.current,
      "parcel-envelopes",
      envelopes ?? EMPTY_COLLECTION,
    );
  }, [
    envelopes,
    mapReady,
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
      "parcel-constraints",
      constraints ?? EMPTY_COLLECTION,
    );
  }, [
    constraints,
    mapReady,
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
      "parcel-grid-evidence",
      gridEvidence ?? EMPTY_COLLECTION,
    );
  }, [
    gridEvidence,
    mapReady,
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
      "parcel-site-evidence",
      siteEvidence ?? EMPTY_COLLECTION,
    );
  }, [
    siteEvidence,
    mapReady,
  ]);


  useEffect(() => {
    if (
      !mapReady
      || !mapRef.current
    ) {
      return;
    }

    applyParcelView(
      mapRef.current,
      parcelView,
    );
  }, [
    mapReady,
    parcelView,
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
      "parcel-planning-evidence",
      planningEvidence ?? EMPTY_COLLECTION,
    );
  }, [
    planningEvidence,
    mapReady,
  ]);


  function loadSelectedZone(): void {
    if (!selectedZoneId) {
      return;
    }

    setParcelDetail(null);
    setDetailError(null);
    void loadZone(
      selectedZoneId
    );
  }


  return (
    <div className="parcel-app">
      <header className="parcel-topbar">
        <div>
          <span className="parcel-kicker">
            AERIS Maryland {AERIS_RELEASE_LABEL}
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

          {parcelView === "site" && (
            <div className="parcel-site-legend">
              <strong>
                Physical site feasibility
              </strong>

              <div>
                <span className="site-swatch strong" />
                Strong preliminary site
              </div>

              <div>
                <span className="site-swatch promising" />
                Promising preliminary site
              </div>

              <div>
                <span className="site-swatch constrained" />
                Physical review required
              </div>

              <div>
                <span className="site-swatch ineligible" />
                Not eligible for site comparison
              </div>

              <div>
                <span className="site-swatch wetlands" />
                Mapped wetlands
              </div>

              <div>
                <span className="site-swatch slope" />
                Steep-slope screen
              </div>

              <div>
                <span className="site-swatch assemblage" />
                Multi-parcel assemblage
              </div>

              <p>
                Site geometry is preliminary. Field delineation, legal
                access, grading, survey, and parcel control remain
                unconfirmed.
              </p>
            </div>
          )}

          {parcelView === "planning" && (
            <div className="parcel-planning-legend">
              <strong>
                Statewide planning context
              </strong>

              <div>
                <span className="planning-swatch pfa" />
                Priority Funding Area
              </div>

              <div>
                <span className="planning-swatch critical" />
                Critical Area
              </div>

              <div>
                <span className="planning-swatch enterprise" />
                Enterprise zone
              </div>

              <div>
                <span className="planning-swatch sustainable" />
                Sustainable community
              </div>

              <div>
                <span className="planning-swatch municipal" />
                Municipal boundary
              </div>

              <p>
                These overlays do not establish
                zoning approval or permitted use.
              </p>
            </div>
          )}

          {parcelView === "grid" && (
            <div className="parcel-grid-legend">
              <strong>
                Public grid context
              </strong>

              <div>
                <span className="grid-swatch extra-high" />
                345 kV and above
              </div>

              <div>
                <span className="grid-swatch high" />
                230–344 kV
              </div>

              <div>
                <span className="grid-swatch regional" />
                115–229 kV
              </div>

              <div>
                <span className="grid-swatch subtransmission" />
                69–114 kV
              </div>

              <div>
                <span className="grid-swatch substation" />
                Mapped substation
              </div>

              <p>
                Voltage and proximity do not
                establish available capacity.
              </p>
            </div>
          )}

          {parcelView === "constraints" && (
            <div className="parcel-constraint-legend">
              <div>
                <span className="constraint-swatch water" />
                Surface water
              </div>

              <div>
                <span className="constraint-swatch protected" />
                Protected land
              </div>

              <div>
                <span className="constraint-swatch flood" />
                SFHA screening
              </div>

              <div>
                <span className="constraint-swatch runway" />
                Physical runway conflict
              </div>

              <div>
                <span className="constraint-swatch aviation-review" />
                FAA notice-distance screen
              </div>
            </div>
          )}

          {loadingParcels && (
            <div className="parcel-loading">
              <strong>
                Building {job?.current_stage ?? "parcel scope"}…
              </strong>
              <span>
                {Math.round((job?.progress ?? 0) * 100)}%
              </span>
            </div>
          )}
        </section>

        <aside className="parcel-sidebar">
          {(scopeError || detailError) && (
            <section className="parcel-error">
              <strong>
                Parcel explorer warning
              </strong>

              <p>
                {scopeError ?? detailError}
              </p>
            </section>
          )}

          <ParcelControls
            zoneOptions={zoneOptions}
            selectedZoneId={selectedZoneId}
            loading={loadingParcels}
            parcels={parcels}
            artifacts={artifacts}
            parcelView={parcelView}
            onZoneChange={setSelectedZoneId}
            onLoad={loadSelectedZone}
            onViewChange={setParcelView}
          />

          <SiteCandidateComparison
            scopeId={
              parcels?.metadata.scope.scope_id
              ?? null
            }
            candidates={
              siteEvidence?.metadata.top_candidates
              ?? []
            }
          />

          <ParcelDetails
            parcel={parcelDetail}
            loading={loadingDetail}
          />
        </aside>
      </main>
    </div>
  );
}
