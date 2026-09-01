from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import GeometryCollection, make_valid, set_precision, union_all

from analysis.common.geometry import repair_invalid_geometries
from analysis.common.geopackage import write_geopackage_atomic
from analysis.common.io import (
    atomic_write_json,
    file_sha256,
    load_yaml,
    read_json,
    resolve_path,
)
from analysis.parcels.envelope_pipeline import envelope_paths, load_yaml as load_envelope_yaml
from analysis.parcels.pipeline import (
    load_config as load_parcel_config,
    parcel_scope_paths,
)
from analysis.site_feasibility.assemblages import (
    CandidateThresholds,
    build_assemblages,
    candidate_eligibility,
    classify_site,
    largest_component,
    polygon_components,
    right_of_way_indicator,
    transparent_candidate_score,
)
from analysis.site_feasibility.raster import (
    TerrainRasterPaths,
    export_scope_terrain,
    threshold_polygons,
    zonal_raster_statistics,
)
from analysis.site_feasibility.sources import (
    ScopedSourceResult,
    download_scoped_layer,
    stable_hash,
)


@dataclass(frozen=True)
class SiteFeasibilityPaths:
    output: Path
    manifest: Path
    raw_scope: Path
    cache_scope: Path
    terrain: TerrainRasterPaths


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def site_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
    scope_id: str,
) -> SiteFeasibilityPaths:
    raw_root = resolve_path(
        project_directory,
        config["outputs"]["raw_scope_directory"]["path"],
    )
    cache_root = resolve_path(
        project_directory,
        config["outputs"]["cache_directory"]["path"],
    )
    derived_root = resolve_path(
        project_directory,
        config["outputs"]["derived_directory"]["path"],
    )
    manifest_root = resolve_path(
        project_directory,
        config["outputs"]["manifest_directory"]["path"],
    )
    raw_scope = raw_root / scope_id
    cache_scope = cache_root / scope_id
    return SiteFeasibilityPaths(
        output=derived_root / f"{scope_id}.gpkg",
        manifest=manifest_root / f"{scope_id}.json",
        raw_scope=raw_scope,
        cache_scope=cache_scope,
        terrain=TerrainRasterPaths(
            dem=raw_scope / "terrain_dem.tif",
            slope=raw_scope / "terrain_slope_percent.tif",
            metadata=raw_scope / "terrain.json",
            tiles_directory=cache_scope / "terrain_tiles",
        ),
    )


def clean_polygonal(geometry, precision_m: float):
    if geometry is None or geometry.is_empty:
        return GeometryCollection()
    result = make_valid(geometry)
    if precision_m > 0:
        result = set_precision(result, precision_m)
    return make_valid(result)


def empty_layer(*, crs: str, columns: list[str]) -> gpd.GeoDataFrame:
    values = {column: [] for column in columns if column != "geometry"}
    values["geometry"] = []
    return gpd.GeoDataFrame(values, geometry="geometry", crs=crs)


def safe_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "t", "yes", "y", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "0", ""}:
            return False
    return bool(value)


def normalized_column(frame: pd.DataFrame, *candidates: str) -> pd.Series:
    lookup = {str(column).casefold(): str(column) for column in frame.columns}
    for candidate in candidates:
        actual = lookup.get(candidate.casefold())
        if actual is not None:
            return (
                frame[actual]
                .astype("string")
                .fillna("")
                .str.strip()
            )
    return pd.Series("", index=frame.index, dtype="string")


def normalize_roads(
    results: list[tuple[str, int, ScopedSourceResult]],
    *,
    target_crs: str,
) -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    for road_class, road_rank, result in results:
        if result.frame.empty:
            continue
        frame = result.frame.copy()
        frame["evidence_kind"] = "ROAD_CENTERLINE"
        frame["road_class"] = road_class.upper()
        frame["road_rank"] = int(road_rank)
        frame["road_name"] = normalized_column(frame, "ROADNAMESHA")
        frame["route_prefix"] = normalized_column(frame, "ID_PREFIX")
        frame["route_number"] = normalized_column(frame, "ID_RTE_NO")
        frame["route_id"] = normalized_column(
            frame,
            "ROUTEID_RH",
            "ROUTEID",
            "CENTERLINEID",
            "OBJECTID",
        )
        frame["road_source_id"] = result.source_id
        frames.append(
            frame[
                [
                    "evidence_kind",
                    "road_class",
                    "road_rank",
                    "road_name",
                    "route_prefix",
                    "route_number",
                    "route_id",
                    "road_source_id",
                    "geometry",
                ]
            ]
        )
    if not frames:
        return empty_layer(
            crs=target_crs,
            columns=[
                "evidence_kind",
                "road_class",
                "road_rank",
                "road_name",
                "route_prefix",
                "route_number",
                "route_id",
                "road_source_id",
                "geometry",
            ],
        )
    return gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=target_crs,
    ).drop_duplicates(subset=["road_class", "route_id", "geometry"])


def road_metrics(
    *,
    parcels: gpd.GeoDataFrame,
    site_geometries: gpd.GeoSeries,
    roads: gpd.GeoDataFrame,
    frontage_tolerance_m: float,
    minimum_frontage_proxy_m: float,
    direct_frontage_excluded_classes: tuple[str, ...],
    near_road_threshold_m: float,
    remote_road_threshold_m: float,
    frontage_clip_geometry: Any | None = None,
) -> pd.DataFrame:
    result = pd.DataFrame({"parcel_id": parcels["parcel_id"].astype(str)})
    if roads.empty:
        result["nearest_road_distance_m"] = np.nan
        result["nearest_road_name"] = None
        result["nearest_road_class"] = None
        result["nearest_primary_road_distance_m"] = np.nan
        result["nearest_accessible_road_distance_m"] = np.nan
        result["road_frontage_proxy_m"] = np.nan
        result["limited_access_adjacency_proxy_m"] = np.nan
        result["site_envelope_to_road_distance_m"] = np.nan
        result["road_access_status"] = "ROAD_DATA_UNAVAILABLE"
        result["road_access_confirmed"] = False
        return result

    road_parcel_geometries = gpd.GeoSeries(
        [
            union_all(components)
            if (components := polygon_components(geometry))
            else GeometryCollection()
            for geometry in parcels.geometry
        ],
        index=parcels.index,
        crs=parcels.crs,
    )
    geometry_available = ~road_parcel_geometries.is_empty

    left = parcels[["parcel_id"]].copy()
    left["_parcel_index"] = parcels.index
    left = gpd.GeoDataFrame(
        left,
        geometry=road_parcel_geometries,
        crs=parcels.crs,
    )
    nearest = gpd.sjoin_nearest(
        left,
        roads,
        how="left",
        distance_col="nearest_road_distance_m",
    )
    nearest = (
        nearest.sort_values(
            ["_parcel_index", "nearest_road_distance_m", "road_rank"],
            ascending=[True, True, True],
            na_position="last",
        )
        .drop_duplicates("_parcel_index")
        .set_index("_parcel_index")
    )

    primary = roads.loc[roads["road_rank"].le(3)].copy()
    if primary.empty:
        primary_distance = pd.Series(np.nan, index=parcels.index)
    else:
        primary_join = gpd.sjoin_nearest(
            left,
            primary,
            how="left",
            distance_col="nearest_primary_road_distance_m",
        )
        primary_distance = (
            primary_join.sort_values(
                ["_parcel_index", "nearest_primary_road_distance_m"],
                na_position="last",
            )
            .drop_duplicates("_parcel_index")
            .set_index("_parcel_index")["nearest_primary_road_distance_m"]
        )

    excluded_classes = {
        str(value).strip().upper()
        for value in direct_frontage_excluded_classes
        if str(value).strip()
    }
    accessible_roads = roads.loc[
        ~roads["road_class"].astype("string").fillna("").str.upper().isin(
            excluded_classes
        )
    ].copy()
    limited_access_roads = roads.loc[
        roads["road_class"].astype("string").fillna("").str.upper().isin(
            excluded_classes
        )
    ].copy()

    if accessible_roads.empty:
        accessible_distance = pd.Series(np.nan, index=parcels.index, dtype=float)
    else:
        accessible_join = gpd.sjoin_nearest(
            left,
            accessible_roads,
            how="left",
            distance_col="nearest_accessible_road_distance_m",
        )
        accessible_distance = (
            accessible_join.sort_values(
                ["_parcel_index", "nearest_accessible_road_distance_m", "road_rank"],
                ascending=[True, True, True],
                na_position="last",
            )
            .drop_duplicates("_parcel_index")
            .set_index("_parcel_index")["nearest_accessible_road_distance_m"]
        )

    frontage_values: list[float] = []
    limited_access_values: list[float] = []
    accessible_index = accessible_roads.sindex if not accessible_roads.empty else None
    limited_index = limited_access_roads.sindex if not limited_access_roads.empty else None
    for _, parcel_geometry in road_parcel_geometries.items():
        if parcel_geometry is None or parcel_geometry.is_empty:
            frontage_values.append(np.nan)
            limited_access_values.append(np.nan)
            continue

        boundary = parcel_geometry.boundary
        if boundary is None or boundary.is_empty:
            frontage_values.append(np.nan)
            limited_access_values.append(np.nan)
            continue

        if (
            frontage_clip_geometry is not None
            and not frontage_clip_geometry.is_empty
        ):
            boundary = boundary.intersection(
                frontage_clip_geometry.buffer(
                    frontage_tolerance_m
                )
            )

            if boundary.is_empty:
                frontage_values.append(0.0)
                limited_access_values.append(0.0)
                continue

        boundary_zone = boundary.buffer(
            frontage_tolerance_m
        )
        frontage = 0.0
        if accessible_index is not None:
            candidate_indices = list(
                accessible_index.query(
                    boundary_zone,
                    predicate="intersects",
                )
            )
            if candidate_indices:
                frontage_geometry = union_all(
                    list(
                        accessible_roads.geometry.iloc[
                            candidate_indices
                        ].intersection(
                            boundary_zone
                        )
                    )
                )

                frontage = float(
                    frontage_geometry.length
                )
        frontage_values.append(frontage)

        limited_access = 0.0
        if limited_index is not None:
            limited_indices = list(
                limited_index.query(
                    boundary_zone,
                    predicate="intersects",
                )
            )
            if limited_indices:
                limited_geometry = union_all(
                    list(
                        limited_access_roads.geometry.iloc[
                            limited_indices
                        ].intersection(
                            boundary_zone
                        )
                    )
                )

                limited_access = float(
                    limited_geometry.length
                )
        limited_access_values.append(limited_access)

    site_frame = gpd.GeoDataFrame(
        {
            "_parcel_index": parcels.index,
        },
        geometry=site_geometries,
        crs=parcels.crs,
    )
    site_frame = site_frame.loc[
        site_frame.geometry.notna()
        & ~site_frame.geometry.is_empty
    ]
    site_distance = pd.Series(
        np.nan,
        index=parcels.index,
        dtype=float,
    )
    if not site_frame.empty and not accessible_roads.empty:
        site_join = gpd.sjoin_nearest(
            site_frame,
            accessible_roads[["geometry"]],
            how="left",
            distance_col="site_envelope_to_road_distance_m",
        )
        site_join = (
            site_join.sort_values(
                ["_parcel_index", "site_envelope_to_road_distance_m"],
                na_position="last",
            )
            .drop_duplicates("_parcel_index")
            .set_index("_parcel_index")
        )
        site_distance.loc[site_join.index] = site_join[
            "site_envelope_to_road_distance_m"
        ]

    nearest_distance = nearest["nearest_road_distance_m"].reindex(parcels.index)
    nearest_accessible_distance = accessible_distance.reindex(parcels.index)
    frontage_series = pd.Series(frontage_values, index=parcels.index)
    limited_access_series = pd.Series(limited_access_values, index=parcels.index)
    status = pd.Series(
        np.select(
            [
                nearest_accessible_distance.le(frontage_tolerance_m)
                & frontage_series.ge(minimum_frontage_proxy_m),
                nearest_accessible_distance.le(near_road_threshold_m),
                nearest_accessible_distance.le(remote_road_threshold_m),
                limited_access_series.ge(minimum_frontage_proxy_m),
            ],
            [
                "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                "NEAR_MAPPED_PUBLIC_ROAD",
                "DISTANT_MAPPED_PUBLIC_ROAD",
                "LIMITED_ACCESS_ROAD_ADJACENCY_REVIEW_REQUIRED",
            ],
            default="REMOTE_FROM_MAPPED_PUBLIC_ROAD",
        ),
        index=parcels.index,
        dtype="object",
    )
    status.loc[
        ~geometry_available
    ] = "PARCEL_GEOMETRY_UNAVAILABLE"

    result["nearest_road_distance_m"] = nearest_distance.to_numpy()
    result["nearest_road_name"] = nearest["road_name"].reindex(parcels.index).to_numpy()
    result["nearest_road_class"] = nearest["road_class"].reindex(parcels.index).to_numpy()
    result["nearest_primary_road_distance_m"] = primary_distance.reindex(parcels.index).to_numpy()
    result["nearest_accessible_road_distance_m"] = nearest_accessible_distance.to_numpy()
    result["road_frontage_proxy_m"] = frontage_series.to_numpy()
    result["limited_access_adjacency_proxy_m"] = limited_access_series.to_numpy()
    result["site_envelope_to_road_distance_m"] = site_distance.to_numpy()
    result["road_access_status"] = status.to_numpy()
    result["road_access_confirmed"] = False
    return result


def building_metrics(
    *,
    parcels: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    square_meters_per_acre: float,
    source_available: bool,
) -> pd.DataFrame:
    result = pd.DataFrame({"parcel_id": parcels["parcel_id"].astype(str)})
    result["building_reference_count"] = 0
    result["building_reference_overlap_acres"] = np.nan
    result["building_reference_fraction"] = np.nan
    result["building_reference_status"] = "UNAVAILABLE"
    if buildings.empty:
        if source_available:
            result["building_reference_overlap_acres"] = 0.0
            result["building_reference_fraction"] = 0.0
            result["building_reference_status"] = (
                "REFERENCE_SOURCE_AVAILABLE_NO_INTERSECTION"
            )
        return result

    parcel_shapes = parcels[["parcel_id", "geometry"]].copy()
    parcel_shapes["_parcel_index"] = parcels.index
    joined = gpd.sjoin(
        buildings[["geometry"]],
        parcel_shapes,
        how="inner",
        predicate="intersects",
    )
    if joined.empty:
        result["building_reference_overlap_acres"] = 0.0
        result["building_reference_fraction"] = 0.0
        result["building_reference_status"] = "REFERENCE_SOURCE_AVAILABLE"
        return result

    counts = joined.groupby("_parcel_index").size()
    areas: dict[int, float] = {}
    for parcel_index, group in joined.groupby("_parcel_index"):
        geometry = union_all(list(group.geometry))
        parcel_geometry = parcels.geometry.loc[int(parcel_index)]
        areas[int(parcel_index)] = float(
            geometry.intersection(parcel_geometry).area / square_meters_per_acre
        )

    result = result.set_index(parcels.index)
    result.loc[counts.index, "building_reference_count"] = counts.astype(int)
    area_series = pd.Series(areas)
    result.loc[area_series.index, "building_reference_overlap_acres"] = area_series
    result["building_reference_overlap_acres"] = result[
        "building_reference_overlap_acres"
    ].fillna(0.0)
    parcel_area = (
        parcels.geometry.area
        / square_meters_per_acre
    ).replace(
        0,
        np.nan,
    )
    result["building_reference_fraction"] = (
        result["building_reference_overlap_acres"] / parcel_area
    ).clip(0, 1)
    result["building_reference_status"] = "REFERENCE_SOURCE_AVAILABLE"
    return result.reset_index(drop=True)


def redevelopment_burden(
    *,
    existing_indicator: bool,
    source_structure_sq_ft: float | None,
    improvement_value: float | None,
    building_fraction: float | None,
) -> str:
    structure = 0.0 if source_structure_sq_ft is None or not math.isfinite(source_structure_sq_ft) else source_structure_sq_ft
    improvement = 0.0 if improvement_value is None or not math.isfinite(improvement_value) else improvement_value
    fraction = None if building_fraction is None or not math.isfinite(building_fraction) else building_fraction
    if fraction is not None and fraction >= 0.25:
        return "HIGH_REDEVELOPMENT_BURDEN"
    if structure >= 100000 or improvement >= 10_000_000:
        return "HIGH_REDEVELOPMENT_BURDEN"
    if existing_indicator or (fraction is not None and fraction >= 0.05):
        return "MODERATE_REDEVELOPMENT_BURDEN"
    if fraction is not None:
        return "LOW_MAPPED_REDEVELOPMENT_BURDEN"
    return "REDEVELOPMENT_BURDEN_UNKNOWN"


def candidate_thresholds(config: dict[str, Any]) -> CandidateThresholds:
    classes = config["analysis"]["candidate_classes"]
    return CandidateThresholds(
        strong_largest_acres=float(classes["strong"]["largest_contiguous_acres"]),
        strong_maximum_steep_fraction=float(classes["strong"]["maximum_steep_fraction"]),
        strong_maximum_wetland_fraction=float(classes["strong"]["maximum_wetland_fraction"]),
        strong_maximum_building_fraction=float(classes["strong"]["maximum_building_fraction"]),
        strong_road_access=tuple(classes["strong"]["road_access"]),
        promising_largest_acres=float(classes["promising"]["largest_contiguous_acres"]),
        promising_maximum_steep_fraction=float(classes["promising"]["maximum_steep_fraction"]),
        promising_maximum_wetland_fraction=float(classes["promising"]["maximum_wetland_fraction"]),
        promising_road_access=tuple(classes["promising"]["road_access"]),
        limited_minimum_acres=float(classes["limited_minimum_acres"]),
    )


def _source_metadata(result: ScopedSourceResult) -> dict[str, Any]:
    return result.metadata


def build_site_feasibility(
    *,
    config_path: Path,
    scope_id: str,
    refresh: bool = False,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()

    def report(stage: str, progress: float) -> None:
        if progress_callback is not None:
            progress_callback(stage, min(max(float(progress), 0.0), 1.0))

    report("loading_inputs", 0.02)
    config_path = config_path.resolve()
    config = load_yaml(config_path)
    project_directory = config_path.parents[2]
    paths = site_paths(
        config=config,
        project_directory=project_directory,
        scope_id=scope_id,
    )

    parcel_config_path = resolve_path(
        project_directory,
        config["inputs"]["parcel_config"]["path"],
    )
    parcel_config = load_parcel_config(parcel_config_path)
    parcel_paths = parcel_scope_paths(
        config=parcel_config,
        project_directory=project_directory,
        scope_id=scope_id,
    )
    envelope_config_path = resolve_path(
        project_directory,
        config["inputs"]["envelope_config"]["path"],
    )
    envelope_config = load_envelope_yaml(envelope_config_path)
    envelope_output = envelope_paths(
        config=envelope_config,
        project_directory=project_directory,
        scope_id=scope_id,
    )
    if not parcel_paths.normalized_output.exists():
        raise RuntimeError(f"Parcel scope has not been built: {scope_id}")
    if not envelope_output.output.exists():
        raise RuntimeError(
            f"Development envelopes have not been built for scope: {scope_id}"
        )

    config_checksum = file_sha256(config_path)
    parcel_checksum = file_sha256(
        parcel_paths.normalized_output
    )
    envelope_checksum = file_sha256(
        envelope_output.output
    )

    implementation_root = (
        Path(__file__).resolve().parent
    )

    implementation_checksum = stable_hash(
        {
            source.name: file_sha256(source)
            for source
            in sorted(
                implementation_root.glob("*.py")
            )
        }
    )
    if not refresh and paths.output.exists() and paths.manifest.exists():
        current = read_json(paths.manifest)
        if (
            current.get(
                "config_checksum"
            ) == config_checksum
            and current.get(
                "parcel_scope_checksum"
            ) == parcel_checksum
            and current.get(
                "envelope_checksum"
            ) == envelope_checksum
            and current.get(
                "implementation_checksum"
            ) == implementation_checksum
        ):
            print(f"[Site feasibility] Using current scope {scope_id}", flush=True)
            return current

    target_crs = str(config["analysis"]["target_crs"])
    square_meters_per_acre = float(config["analysis"]["square_meters_per_acre"])
    precision_m = float(config["analysis"]["geometry_precision_m"])
    minimum_component_acres = float(config["analysis"]["minimum_site_component_acres"])

    parcels = gpd.read_file(
        parcel_paths.normalized_output,
        layer="parcels",
    ).to_crs(target_crs)
    parcels = repair_invalid_geometries(parcels, name="site_feasibility_parcels").reset_index(drop=True)

    base_envelopes = gpd.read_file(
        envelope_output.output,
        layer="development_envelopes",
    ).to_crs(target_crs)
    base_envelopes = repair_invalid_geometries(base_envelopes, name="base_development_envelopes")

    base_geometry_lookup = base_envelopes.set_index("parcel_id").geometry
    base_geometries = gpd.GeoSeries(
        [
            base_geometry_lookup.get(parcel_id, GeometryCollection())
            for parcel_id in parcels["parcel_id"]
        ],
        index=parcels.index,
        crs=target_crs,
    )
    analysis_scope_parts = [
        geometry
        for geometry in base_geometries
        if (
            geometry is not None
            and not geometry.is_empty
        )
    ]

    scope_geometry = (
        clean_polygonal(
            union_all(
                analysis_scope_parts
            ),
            precision_m,
        )
        if analysis_scope_parts
        else clean_polygonal(
            union_all(
                list(
                    parcels.geometry
                )
            ),
            precision_m,
        )
    )

    scope_bounds = tuple(
        float(value)
        for value in scope_geometry.bounds
    )
    paths.raw_scope.mkdir(parents=True, exist_ok=True)
    paths.cache_scope.mkdir(parents=True, exist_ok=True)

    domain_status: dict[str, dict[str, Any]] = {}
    source_metadata: dict[str, Any] = {}

    report("wetlands", 0.12)
    # --- Wetlands -----------------------------------------------------
    wetland_frames: list[gpd.GeoDataFrame] = []
    wetland_union = GeometryCollection()
    wssc_buffer_union = GeometryCollection()
    wetlands_config = config["inputs"]["wetlands"]
    if bool(wetlands_config.get("enabled", False)):
        try:
            scope_with_buffer = scope_geometry.buffer(float(wetlands_config["scope_buffer_m"]))
            for source_id, layer_config in wetlands_config["layers"].items():
                result = download_scoped_layer(
                    source_id=f"wetlands_{source_id}",
                    layer_url=f"{str(wetlands_config['service_url']).rstrip('/')}/{int(layer_config['id'])}",
                    desired_fields=list(layer_config.get("fields", [])),
                    scope_geometry=scope_with_buffer,
                    scope_crs=target_crs,
                    target_crs=target_crs,
                    cache_root=paths.cache_scope / "vectors",
                    page_size=int(wetlands_config["page_size"]),
                    timeout_seconds=int(wetlands_config["timeout_seconds"]),
                    where=str(
                        layer_config.get(
                            "where",
                            "1=1",
                        )
                    ),
                    refresh=refresh,
                )
                frame = result.frame.copy()
                if not frame.empty:
                    frame["evidence_kind"] = "SITE_CONSTRAINT"
                    frame["constraint_id"] = f"wetlands_{source_id}"
                    frame["constraint_label"] = str(layer_config["name"])
                    frame["source_last_updated"] = str(layer_config.get("source_last_updated", ""))
                    frame["subtract_from_site_envelope"] = bool(layer_config.get("subtract_from_site_envelope", True))
                    wetland_frames.append(frame)
                    geometry = clean_polygonal(union_all(list(frame.geometry)), precision_m)
                    if source_id == "special_state_concern":
                        buffer_m = float(layer_config.get("buffer_m", 0.0))
                        wssc_buffer_union = clean_polygonal(geometry.buffer(buffer_m), precision_m)
                    else:
                        wetland_union = clean_polygonal(
                            union_all([wetland_union, geometry]),
                            precision_m,
                        )
                source_metadata[f"wetlands_{source_id}"] = _source_metadata(result)
            wetland_union = clean_polygonal(
                union_all([wetland_union, wssc_buffer_union]),
                precision_m,
            )
            domain_status["wetlands"] = {"state": "ready", "error": None}
        except Exception as error:  # noqa: BLE001
            domain_status["wetlands"] = {
                "state": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
    else:
        domain_status["wetlands"] = {"state": "disabled", "error": None}

    report("roads", 0.28)
    # --- Roads --------------------------------------------------------
    roads = empty_layer(crs=target_crs, columns=["evidence_kind", "geometry"])
    roads_config = config["inputs"]["roads"]
    road_results: list[tuple[str, int, ScopedSourceResult]] = []
    if bool(roads_config.get("enabled", False)):
        try:
            road_scope = scope_geometry.buffer(float(roads_config["scope_buffer_m"]))
            for road_class, layer_config in roads_config["layers"].items():
                result = download_scoped_layer(
                    source_id=f"roads_{road_class}",
                    layer_url=f"{str(roads_config['service_url']).rstrip('/')}/{int(layer_config['id'])}",
                    desired_fields=list(roads_config["fields"]),
                    scope_geometry=road_scope,
                    scope_crs=target_crs,
                    target_crs=target_crs,
                    cache_root=paths.cache_scope / "vectors",
                    page_size=int(roads_config["page_size"]),
                    timeout_seconds=int(roads_config["timeout_seconds"]),
                    refresh=refresh,
                )
                road_results.append((road_class, int(layer_config["rank"]), result))
                source_metadata[f"roads_{road_class}"] = _source_metadata(result)
            roads = normalize_roads(road_results, target_crs=target_crs)
            domain_status["roads"] = {"state": "ready", "error": None}
        except Exception as error:  # noqa: BLE001
            domain_status["roads"] = {
                "state": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
    else:
        domain_status["roads"] = {"state": "disabled", "error": None}

    report("building_reference", 0.40)
    # --- Building reference -----------------------------------------
    buildings = empty_layer(crs=target_crs, columns=["evidence_kind", "geometry"])
    buildings_config = config["inputs"]["buildings"]
    if bool(buildings_config.get("enabled", False)):
        try:
            result = download_scoped_layer(
                source_id="buildings_reference",
                layer_url=str(buildings_config["layer_url"]),
                desired_fields=["OBJECTID"],
                scope_geometry=scope_geometry.buffer(float(buildings_config["scope_buffer_m"])),
                scope_crs=target_crs,
                target_crs=target_crs,
                cache_root=paths.cache_scope / "vectors",
                page_size=int(buildings_config["page_size"]),
                timeout_seconds=int(buildings_config["timeout_seconds"]),
                refresh=refresh,
                maximum_features=int(buildings_config["maximum_scope_features"]),
            )
            buildings = result.frame.copy()
            if not buildings.empty:
                buildings["evidence_kind"] = "BUILDING_REFERENCE"
                buildings["source_role"] = str(buildings_config["source_role"])
            source_metadata["buildings_reference"] = _source_metadata(result)
            domain_status["buildings"] = {"state": "ready", "error": None}
        except Exception as error:  # noqa: BLE001
            domain_status["buildings"] = {
                "state": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
    else:
        domain_status["buildings"] = {"state": "disabled", "error": None}

    report("terrain", 0.50)
    # --- Terrain ------------------------------------------------------
    dem_stats: list[dict[str, Any]] = []
    slope_stats: list[dict[str, Any]] = []
    steep_polygons = empty_layer(crs=target_crs, columns=["threshold", "geometry"])
    severe_polygons = empty_layer(crs=target_crs, columns=["threshold", "geometry"])
    terrain_config = config["inputs"]["terrain"]
    terrain_metadata: dict[str, Any] | None = None
    if bool(terrain_config.get("enabled", False)):
        try:
            terrain_fingerprint = stable_hash(
                {
                    "scope_bounds": scope_bounds,
                    "source": terrain_config,
                    "parcel_checksum": parcel_checksum,
                    "envelope_checksum": envelope_checksum,
                }
            )
            terrain_metadata = export_scope_terrain(
                image_server_url=str(terrain_config["image_server_url"]),
                source_name=str(terrain_config["source_name"]),
                source_last_updated=str(terrain_config["source_last_updated"]),
                bounds=scope_bounds,
                target_crs_wkid=int(target_crs.split(":")[-1]),
                target_pixel_size_m=float(terrain_config["target_pixel_size_m"]),
                maximum_pixel_size_m=float(terrain_config["maximum_pixel_size_m"]),
                maximum_total_pixels=int(terrain_config["maximum_total_pixels"]),
                maximum_tile_pixels=int(terrain_config["maximum_tile_pixels"]),
                raster_function=str(terrain_config["dem_raster_function"]),
                timeout_seconds=int(terrain_config["timeout_seconds"]),
                paths=paths.terrain,
                fingerprint=terrain_fingerprint,
                refresh=refresh,
            )
            dem_stats = zonal_raster_statistics(
                geometries=base_geometries,
                raster_path=paths.terrain.dem,
                quantiles=(0.5,),
            )
            steep_threshold = float(terrain_config["steep_slope_threshold_percent"])
            severe_threshold = float(terrain_config["severe_slope_threshold_percent"])
            slope_stats = zonal_raster_statistics(
                geometries=base_geometries,
                raster_path=paths.terrain.slope,
                quantiles=(0.5, 0.9),
                thresholds=(steep_threshold, severe_threshold),
            )
            minimum_polygon_area_sq_m = float(terrain_config["minimum_polygon_area_acres"]) * square_meters_per_acre
            steep_polygons = threshold_polygons(
                raster_path=paths.terrain.slope,
                threshold=steep_threshold,
                minimum_area_sq_m=minimum_polygon_area_sq_m,
                clip_geometry=scope_geometry,
            )
            severe_polygons = threshold_polygons(
                raster_path=paths.terrain.slope,
                threshold=severe_threshold,
                minimum_area_sq_m=minimum_polygon_area_sq_m,
                clip_geometry=scope_geometry,
            )
            domain_status["terrain"] = {"state": "ready", "error": None}
            source_metadata["terrain"] = terrain_metadata
        except Exception as error:  # noqa: BLE001
            domain_status["terrain"] = {
                "state": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
    else:
        domain_status["terrain"] = {"state": "disabled", "error": None}

    steep_union = (
        clean_polygonal(union_all(list(steep_polygons.geometry)), precision_m)
        if not steep_polygons.empty
        else GeometryCollection()
    )
    if not bool(terrain_config.get("subtract_steep_slope_from_site_envelope", True)):
        steep_union = GeometryCollection()

    report("site_envelopes", 0.74)
    # --- Final site envelopes ---------------------------------------
    subtractive_geometries = [geometry for geometry in (wetland_union, steep_union) if not geometry.is_empty]
    subtractive_union = (
        clean_polygonal(union_all(subtractive_geometries), precision_m)
        if subtractive_geometries
        else GeometryCollection()
    )
    final_geometries = gpd.GeoSeries(
        [
            clean_polygonal(
                geometry.difference(subtractive_union)
                if not subtractive_union.is_empty and geometry is not None and not geometry.is_empty
                else geometry,
                precision_m,
            )
            for geometry in base_geometries
        ],
        index=parcels.index,
        crs=target_crs,
    )
    largest_geometries = gpd.GeoSeries(
        [largest_component(geometry) for geometry in final_geometries],
        index=parcels.index,
        crs=target_crs,
    )
    base_area_acres = base_geometries.area / square_meters_per_acre
    final_area_acres = final_geometries.area / square_meters_per_acre
    largest_area_acres = largest_geometries.area / square_meters_per_acre

    wetland_overlap_acres = pd.Series(
        [
            float(geometry.intersection(wetland_union).area / square_meters_per_acre)
            if not wetland_union.is_empty and geometry is not None and not geometry.is_empty
            else 0.0
            for geometry in base_geometries
        ],
        index=parcels.index,
    )
    wssc_overlap_acres = pd.Series(
        [
            float(geometry.intersection(wssc_buffer_union).area / square_meters_per_acre)
            if not wssc_buffer_union.is_empty and geometry is not None and not geometry.is_empty
            else 0.0
            for geometry in base_geometries
        ],
        index=parcels.index,
    )
    steep_overlap_acres = pd.Series(
        [
            float(geometry.intersection(steep_union).area / square_meters_per_acre)
            if not steep_union.is_empty and geometry is not None and not geometry.is_empty
            else 0.0
            for geometry in base_geometries
        ],
        index=parcels.index,
    )

    road_data = road_metrics(
        parcels=parcels,
        site_geometries=final_geometries,
        roads=roads,
        frontage_tolerance_m=float(roads_config["frontage_tolerance_m"]),
        minimum_frontage_proxy_m=float(roads_config["minimum_frontage_proxy_m"]),
        direct_frontage_excluded_classes=tuple(
            str(value).strip().upper()
            for value in roads_config.get(
                "direct_frontage_excluded_classes",
                [],
            )
        ),
        near_road_threshold_m=float(roads_config["near_road_threshold_m"]),
        remote_road_threshold_m=float(
            roads_config[
                "remote_road_threshold_m"
            ]
        ),
        frontage_clip_geometry=scope_geometry,
    )

    building_parcels = parcels.copy()
    building_parcels.geometry = (
        base_geometries
    )

    building_data = building_metrics(
        parcels=building_parcels,
        buildings=buildings,
        square_meters_per_acre=square_meters_per_acre,
        source_available=(
            domain_status["buildings"]["state"] == "ready"
        ),
    )

    parcel_analysis = parcels.copy()
    parcel_analysis["base_development_envelope_acres"] = base_area_acres.round(6)
    parcel_analysis["mapped_wetland_overlap_acres"] = wetland_overlap_acres.round(6)
    parcel_analysis["mapped_wetland_fraction"] = (
        wetland_overlap_acres / base_area_acres.replace(0, np.nan)
    ).clip(0, 1).round(6)
    parcel_analysis["wssc_screening_overlap_acres"] = wssc_overlap_acres.round(6)
    parcel_analysis["steep_slope_overlap_acres"] = steep_overlap_acres.round(6)
    parcel_analysis["steep_slope_fraction"] = (
        steep_overlap_acres / base_area_acres.replace(0, np.nan)
    ).clip(0, 1).round(6)
    parcel_analysis["final_site_area_acres"] = final_area_acres.round(6)
    parcel_analysis["final_site_fraction_of_base_envelope"] = (
        final_area_acres / base_area_acres.replace(0, np.nan)
    ).clip(0, 1).round(6)
    parcel_analysis["largest_contiguous_site_acres"] = largest_area_acres.round(6)
    parcel_analysis["site_component_count"] = [
        sum(
            component.area / square_meters_per_acre >= minimum_component_acres
            for component in polygon_components(geometry)
        )
        for geometry in final_geometries
    ]

    if dem_stats:
        parcel_analysis["terrain_sample_count"] = [record["count"] for record in dem_stats]
        parcel_analysis["elevation_minimum_m"] = [record["minimum"] for record in dem_stats]
        parcel_analysis["elevation_maximum_m"] = [record["maximum"] for record in dem_stats]
        parcel_analysis["elevation_mean_m"] = [record["mean"] for record in dem_stats]
        parcel_analysis["elevation_range_m"] = (
            pd.to_numeric(parcel_analysis["elevation_maximum_m"], errors="coerce")
            - pd.to_numeric(parcel_analysis["elevation_minimum_m"], errors="coerce")
        )
    else:
        for column in (
            "terrain_sample_count",
            "elevation_minimum_m",
            "elevation_maximum_m",
            "elevation_mean_m",
            "elevation_range_m",
        ):
            parcel_analysis[column] = np.nan

    if slope_stats:
        parcel_analysis["slope_mean_percent"] = [record["mean"] for record in slope_stats]
        parcel_analysis["slope_median_percent"] = [record.get("q50") for record in slope_stats]
        parcel_analysis["slope_p90_percent"] = [record.get("q90") for record in slope_stats]
        steep_key = str(float(terrain_config["steep_slope_threshold_percent"])).replace(".", "_")
        severe_key = str(float(terrain_config["severe_slope_threshold_percent"])).replace(".", "_")
        parcel_analysis["terrain_steep_pixel_fraction"] = [
            record.get(f"fraction_ge_{steep_key}") for record in slope_stats
        ]
        parcel_analysis["terrain_severe_pixel_fraction"] = [
            record.get(f"fraction_ge_{severe_key}") for record in slope_stats
        ]
    else:
        for column in (
            "slope_mean_percent",
            "slope_median_percent",
            "slope_p90_percent",
            "terrain_steep_pixel_fraction",
            "terrain_severe_pixel_fraction",
        ):
            parcel_analysis[column] = np.nan

    parcel_analysis = parcel_analysis.merge(road_data, on="parcel_id", how="left", validate="one_to_one")
    parcel_analysis = parcel_analysis.merge(building_data, on="parcel_id", how="left", validate="one_to_one")
    parcel_analysis["redevelopment_burden_class"] = [
        redevelopment_burden(
            existing_indicator=safe_bool(
                row.get("existing_development_indicator", False)
            ),
            source_structure_sq_ft=(
                None
                if pd.isna(row.get("source_structure_sq_ft"))
                else float(row.get("source_structure_sq_ft"))
            ),
            improvement_value=(
                None
                if pd.isna(row.get("appraised_improvement_value"))
                else float(row.get("appraised_improvement_value"))
            ),
            building_fraction=(
                None
                if pd.isna(row.get("building_reference_fraction"))
                else float(row.get("building_reference_fraction"))
            ),
        )
        for _, row in parcel_analysis.iterrows()
    ]
    parcel_analysis["terrain_data_status"] = domain_status["terrain"]["state"].upper()
    parcel_analysis["wetland_data_status"] = domain_status["wetlands"]["state"].upper()
    parcel_analysis["road_data_status"] = domain_status["roads"]["state"].upper()
    parcel_analysis["building_reference_data_status"] = domain_status["buildings"]["state"].upper()
    parcel_analysis["road_access_confirmed"] = False
    parcel_analysis["wetland_delineation_confirmed"] = False
    parcel_analysis["legal_buildability_confirmed"] = False

    thresholds = candidate_thresholds(config)
    parcel_analysis["site_feasibility_class"] = [
        classify_site(
            largest_contiguous_acres=float(row["largest_contiguous_site_acres"] or 0),
            steep_fraction=(None if pd.isna(row["steep_slope_fraction"]) else float(row["steep_slope_fraction"])),
            wetland_fraction=(None if pd.isna(row["mapped_wetland_fraction"]) else float(row["mapped_wetland_fraction"])),
            building_fraction=(None if pd.isna(row["building_reference_fraction"]) else float(row["building_reference_fraction"])),
            road_access_status=str(row.get("road_access_status") or ""),
            thresholds=thresholds,
        )
        for _, row in parcel_analysis.iterrows()
    ]
    parcel_analysis[
        "right_of_way_flag"
    ] = [
        right_of_way_indicator(
            account_id=row.get(
                "account_id",
                "",
            ),
            parcel_id=row.get(
                "parcel_id",
                "",
            ),
        )
        for _, row
        in parcel_analysis.iterrows()
    ]

    right_of_way_mask = (
        parcel_analysis[
            "right_of_way_flag"
        ].fillna(False).astype(bool)
    )

    parcel_analysis.loc[
        right_of_way_mask,
        [
            "road_frontage_proxy_m",
            "limited_access_adjacency_proxy_m",
            "site_envelope_to_road_distance_m",
        ],
    ] = np.nan

    parcel_analysis.loc[
        right_of_way_mask,
        "road_access_status",
    ] = "RIGHT_OF_WAY_NOT_EVALUATED"

    eligibility = [
        candidate_eligibility(
            public_land_flag=safe_bool(row.get("public_land_flag", False)),
            institutional_use_flag=safe_bool(
                row.get("institutional_use_flag", False)
            ),
            statewide_hard_excluded=safe_bool(
                row.get(
                    "statewide_hard_excluded",
                    False,
                )
            ),
            site_feasibility_class=str(
                row[
                    "site_feasibility_class"
                ]
            ),
            right_of_way_flag=safe_bool(
                row.get(
                    "right_of_way_flag",
                    False,
                )
            ),
        )
        for _, row in parcel_analysis.iterrows()
    ]
    parcel_analysis["candidate_eligible"] = [value[0] for value in eligibility]
    parcel_analysis["candidate_status"] = [value[1] for value in eligibility]
    parcel_analysis["candidate_status_reason"] = [value[2] for value in eligibility]

    parcel_analysis["site_candidate_score"] = [
        transparent_candidate_score(
            largest_contiguous_acres=float(row["largest_contiguous_site_acres"] or 0),
            steep_fraction=(None if pd.isna(row["steep_slope_fraction"]) else float(row["steep_slope_fraction"])),
            wetland_fraction=(None if pd.isna(row["mapped_wetland_fraction"]) else float(row["mapped_wetland_fraction"])),
            building_fraction=(None if pd.isna(row["building_reference_fraction"]) else float(row["building_reference_fraction"])),
            road_access_status=str(row.get("road_access_status") or ""),
        )
        for _, row in parcel_analysis.iterrows()
    ]
    parcel_analysis["candidate_kind"] = "PARCEL"
    parcel_analysis["candidate_id"] = parcel_analysis["parcel_id"].astype(str)

    site_envelopes = gpd.GeoDataFrame(
        parcel_analysis.drop(columns="geometry").copy(),
        geometry=final_geometries,
        crs=target_crs,
    )
    site_envelopes = site_envelopes.loc[
        site_envelopes.geometry.notna()
        & ~site_envelopes.geometry.is_empty
        & site_envelopes["final_site_area_acres"].gt(0)
    ].copy()
    site_envelopes["evidence_kind"] = "SITE_ENVELOPE"

    largest_components = gpd.GeoDataFrame(
        parcel_analysis.drop(columns="geometry").copy(),
        geometry=largest_geometries,
        crs=target_crs,
    )
    largest_components = largest_components.loc[
        largest_components.geometry.notna()
        & ~largest_components.geometry.is_empty
        & largest_components["largest_contiguous_site_acres"].gt(0)
    ].copy()
    largest_components["evidence_kind"] = "LARGEST_SITE_COMPONENT"

    constraints_frames: list[gpd.GeoDataFrame] = []
    for frame in wetland_frames:
        if not frame.empty:
            constraints_frames.append(frame)
    if not steep_polygons.empty:
        steep_layer = steep_polygons.copy()
        steep_layer["evidence_kind"] = "SITE_CONSTRAINT"
        steep_layer["constraint_id"] = "steep_slope"
        steep_layer["constraint_label"] = (
            f"Slope >= {terrain_config['steep_slope_threshold_percent']} percent"
        )
        steep_layer["subtract_from_site_envelope"] = True
        constraints_frames.append(steep_layer)
    if not severe_polygons.empty:
        severe_layer = severe_polygons.copy()
        severe_layer["evidence_kind"] = "SITE_CONSTRAINT_REVIEW"
        severe_layer["constraint_id"] = "severe_slope"
        severe_layer["constraint_label"] = (
            f"Slope >= {terrain_config['severe_slope_threshold_percent']} percent"
        )
        severe_layer["subtract_from_site_envelope"] = False
        constraints_frames.append(severe_layer)
    site_constraints = (
        gpd.GeoDataFrame(pd.concat(constraints_frames, ignore_index=True), geometry="geometry", crs=target_crs)
        if constraints_frames
        else empty_layer(crs=target_crs, columns=["evidence_kind", "constraint_id", "geometry"])
    )

    report("assemblages", 0.87)
    assemblage_config = config["analysis"]["assemblages"]
    assemblages = (
        build_assemblages(
            parcel_analysis=parcel_analysis,
            site_envelopes=site_envelopes[["parcel_id", "geometry"]],
            square_meters_per_acre=square_meters_per_acre,
            adjacency_gap_m=float(assemblage_config["adjacency_gap_m"]),
            minimum_parcel_site_acres=float(assemblage_config["minimum_parcel_site_acres"]),
            minimum_total_site_acres=float(assemblage_config["minimum_total_site_acres"]),
            minimum_parcel_count=int(assemblage_config["minimum_parcel_count"]),
            maximum_parcel_count=int(assemblage_config["maximum_parcel_count"]),
            maximum_candidates=int(assemblage_config["maximum_candidates"]),
            thresholds=thresholds,
        )
        if bool(assemblage_config.get("enabled", True))
        else empty_layer(crs=target_crs, columns=["assemblage_id", "geometry"])
    )

    report("writing_outputs", 0.95)
    layer_names = config["layers"]
    written_layers = write_geopackage_atomic(
        path=paths.output,
        layers=[
            (layer_names["parcel_analysis"], parcel_analysis),
            (layer_names["site_envelopes"], site_envelopes),
            (layer_names["largest_components"], largest_components),
            (layer_names["site_constraints"], site_constraints),
            (layer_names["roads"], roads),
            (layer_names["buildings_reference"], buildings),
            (layer_names["assemblages"], assemblages),
        ],
        indexes=[
            (layer_names["parcel_analysis"], "parcel_id"),
            (layer_names["site_envelopes"], "parcel_id"),
            (layer_names["assemblages"], "assemblage_id"),
        ],
    )

    parcel_candidates = parcel_analysis[
        [
            "candidate_id",
            "candidate_kind",
            "parcel_id",
            "site_candidate_score",
            "site_feasibility_class",
            "candidate_eligible",
            "candidate_status",
            "candidate_status_reason",
            "final_site_area_acres",
            "largest_contiguous_site_acres",
            "road_access_status",
            "mapped_wetland_fraction",
            "steep_slope_fraction",
            "building_reference_fraction",
            "redevelopment_burden_class",
        ]
    ].copy()
    parcel_candidates = parcel_candidates.rename(
        columns={"site_candidate_score": "candidate_score"}
    )
    assemblage_candidates = (
        assemblages.drop(columns="geometry").copy()
        if not assemblages.empty
        else pd.DataFrame()
    )
    all_candidates = pd.concat(
        [parcel_candidates, assemblage_candidates],
        ignore_index=True,
        sort=False,
    )
    top_candidates = all_candidates.loc[
        all_candidates["candidate_eligible"].fillna(False).astype(bool)
    ].sort_values(
        ["candidate_score", "largest_contiguous_site_acres"],
        ascending=[False, False],
        na_position="last",
    ).head(int(config["api"]["maximum_top_candidates"]))

    manifest = {
        "schema_version": 1,
        "pipeline": "parcel_site_feasibility",
        "pipeline_version": config["pipeline_version"],
        "generated_at_utc": utc_now(),
        "snapshot_label": config["snapshot_label"],
        "scope_id": scope_id,
        "domain_status": domain_status,
        "counts": {
            "parcel_count": len(parcel_analysis),
            "site_envelope_count": len(site_envelopes),
            "site_constraint_feature_count": len(site_constraints),
            "road_feature_count": len(roads),
            "building_reference_feature_count": len(buildings),
            "assemblage_count": len(assemblages),
            "eligible_parcel_candidate_count": int(
                parcel_analysis["candidate_eligible"].sum()
            ),
            "eligible_assemblage_candidate_count": int(
                assemblages.get(
                    "candidate_eligible",
                    pd.Series(False, index=assemblages.index),
                ).fillna(False).astype(bool).sum()
            ),
        },
        "site_feasibility_class_counts": {
            str(key): int(value)
            for key, value in parcel_analysis["site_feasibility_class"].value_counts(dropna=False).items()
        },
        "road_access_status_counts": {
            str(key): int(value)
            for key, value in parcel_analysis["road_access_status"].value_counts(dropna=False).items()
        },
        "statistics": {
            "final_site_area_acres": {
                "total": float(parcel_analysis["final_site_area_acres"].sum()),
                "median": float(parcel_analysis["final_site_area_acres"].median()),
                "maximum": float(parcel_analysis["final_site_area_acres"].max()),
            },
            "largest_contiguous_site_acres": {
                "median": float(parcel_analysis["largest_contiguous_site_acres"].median()),
                "maximum": float(parcel_analysis["largest_contiguous_site_acres"].max()),
            },
        },
        "source_metadata": source_metadata,
        "top_candidates": json.loads(top_candidates.to_json(orient="records")),
        "safeguards": config["safeguards"],
        "interpretation": {
            "allowed_term": "Preliminary physical site-feasibility evidence",
            "not_allowed_terms": [
                "Buildable land",
                "Road access approved",
                "Wetlands cleared",
                "Parcel assembly controlled",
                "Construction ready",
            ],
            "terrain": (
                "Slope is derived from a scoped export of the Maryland statewide LiDAR DEM mosaic. "
                "It is screening evidence and does not replace survey or grading design."
            ),
            "wetlands": (
                "Mapped wetlands are screening evidence only. Field delineation and permitting remain required."
            ),
            "frontage": (
                "Road frontage is a centerline proximity/length proxy, not proof of legal or engineered access."
            ),
            "assemblages": (
                "Assemblages identify spatially contiguous parcel groups. Ownership control and acquisition feasibility are unconfirmed."
            ),
        },
        "config_checksum": config_checksum,
        "parcel_scope_checksum": parcel_checksum,
        "envelope_checksum": envelope_checksum,
        "implementation_checksum": (
            implementation_checksum
        ),
        "written_layers": written_layers,
        "outputs": {"geopackage": str(paths.output.relative_to(project_directory))},
        "output_checksums": {"geopackage": file_sha256(paths.output)},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    paths.manifest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(paths.manifest, manifest)
    report("complete", 1.0)
    print(
        f"[Site feasibility] Complete | {len(parcel_analysis):,} parcels | "
        f"{len(assemblages):,} assemblages | {manifest['elapsed_seconds']:.1f}s",
        flush=True,
    )
    return manifest
