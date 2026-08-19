from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from shapely import (
    GeometryCollection,
    MultiPolygon,
    Polygon,
    make_valid,
    set_precision,
    union_all,
)
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from analysis.parcels.pipeline import (
    file_sha256,
    load_config as load_parcel_config,
    parcel_scope_paths,
    read_json,
    resolve_path,
    scope_from_zone,
)
from analysis.statewide.grid_infrastructure_pipeline import (
    atomic_write_json,
    repair_invalid_geometries,
)


SQUARE_METERS_PER_ACRE = 4046.8564224


@dataclass(frozen=True)
class EnvelopePaths:
    output: Path
    manifest: Path


@dataclass(frozen=True)
class ConstraintResult:
    source_id: str
    label: str
    enabled: bool
    available: bool
    source_path: Path | None
    layer: str | None
    buffer_m: float
    screening_role: str
    source_feature_count: int
    geometry: BaseGeometry
    checksum: str | None


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_yaml(
    path: Path,
) -> dict[str, Any]:
    value = yaml.safe_load(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            f"Expected YAML object: {path}"
        )

    return value


def polygonal_geometry(
    geometry: BaseGeometry | None,
) -> BaseGeometry:
    if (
        geometry is None
        or geometry.is_empty
    ):
        return GeometryCollection()

    fixed = make_valid(
        geometry
    )

    if isinstance(
        fixed,
        (Polygon, MultiPolygon),
    ):
        return fixed

    if isinstance(
        fixed,
        GeometryCollection,
    ):
        polygon_parts: list[
            BaseGeometry
        ] = []

        for part in fixed.geoms:
            if isinstance(
                part,
                (Polygon, MultiPolygon),
            ):
                polygon_parts.append(
                    part
                )

        if not polygon_parts:
            return GeometryCollection()

        return polygonal_geometry(
            union_all(
                polygon_parts
            )
        )

    return GeometryCollection()


def clean_geometry(
    geometry: BaseGeometry | None,
    precision_m: float,
) -> BaseGeometry:
    result = polygonal_geometry(
        geometry
    )

    if (
        result.is_empty
        or precision_m <= 0
    ):
        return result

    result = set_precision(
        result,
        precision_m,
    )

    return polygonal_geometry(
        result
    )


def component_geometries(
    geometry: BaseGeometry,
) -> list[Polygon]:
    cleaned = polygonal_geometry(
        geometry
    )

    if cleaned.is_empty:
        return []

    if isinstance(
        cleaned,
        Polygon,
    ):
        return [cleaned]

    if isinstance(
        cleaned,
        MultiPolygon,
    ):
        return list(
            cleaned.geoms
        )

    return []


def largest_component(
    geometry: BaseGeometry,
    minimum_area_sq_m: float,
) -> BaseGeometry:
    components = [
        component
        for component
        in component_geometries(
            geometry
        )
        if component.area
        >= minimum_area_sq_m
    ]

    if not components:
        return GeometryCollection()

    return max(
        components,
        key=lambda item: item.area,
    )


def component_count(
    geometry: BaseGeometry,
    minimum_area_sq_m: float,
) -> int:
    return sum(
        component.area
        >= minimum_area_sq_m
        for component
        in component_geometries(
            geometry
        )
    )


def envelope_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
    scope_id: str,
) -> EnvelopePaths:
    output_root = resolve_path(
        project_directory,
        config[
            "outputs"
        ][
            "derived_directory"
        ]["path"],
    )

    manifest_root = resolve_path(
        project_directory,
        config[
            "outputs"
        ][
            "manifest_directory"
        ]["path"],
    )

    return EnvelopePaths(
        output=(
            output_root
            / f"{scope_id}.gpkg"
        ),
        manifest=(
            manifest_root
            / f"{scope_id}.json"
        ),
    )


def scope_geometry_from_manifest(
    *,
    parcel_manifest: dict[str, Any],
    parcel_config: dict[str, Any],
    project_directory: Path,
    target_crs: str,
) -> BaseGeometry:
    scope = parcel_manifest[
        "scope"
    ]

    scope_type = scope[
        "scope_type"
    ]

    if scope_type == (
        "candidate_zone"
    ):
        zone_id = scope.get(
            "zone_id"
        )

        if not zone_id:
            raise RuntimeError(
                "Candidate-zone scope is "
                "missing zone_id."
            )

        zone_scope = scope_from_zone(
            config=parcel_config,
            project_directory=(
                project_directory
            ),
            zone_id=str(
                zone_id
            ),
        )

        geometry_wgs84 = (
            zone_scope.geometry_wgs84
        )

    elif scope_type == "bbox":
        bounds = scope[
            "bbox_wgs84"
        ]

        geometry_wgs84 = box(
            float(bounds["west"]),
            float(bounds["south"]),
            float(bounds["east"]),
            float(bounds["north"]),
        )

    else:
        raise RuntimeError(
            "Unsupported parcel scope type: "
            f"{scope_type!r}"
        )

    return (
        gpd.GeoSeries(
            [
                geometry_wgs84
            ],
            crs="EPSG:4326",
        )
        .to_crs(
            target_crs
        )
        .iloc[0]
    )


def load_constraint(
    *,
    source_id: str,
    source_config: dict[str, Any],
    project_directory: Path,
    scope_geometry: BaseGeometry,
    target_crs: str,
    precision_m: float,
) -> ConstraintResult:
    enabled = bool(
        source_config.get(
            "enabled",
            False,
        )
    )

    label = str(
        source_config.get(
            "label",
            source_id,
        )
    )

    layer = source_config.get(
        "layer"
    )

    buffer_m = float(
        source_config.get(
            "buffer_m",
            0.0,
        )
    )

    screening_role = str(
        source_config.get(
            "screening_role",
            "unspecified",
        )
    )

    raw_path = source_config.get(
        "path"
    )

    if not enabled:
        return ConstraintResult(
            source_id=source_id,
            label=label,
            enabled=False,
            available=False,
            source_path=None,
            layer=(
                None
                if layer is None
                else str(layer)
            ),
            buffer_m=buffer_m,
            screening_role=(
                screening_role
            ),
            source_feature_count=0,
            geometry=GeometryCollection(),
            checksum=None,
        )

    if not raw_path:
        raise RuntimeError(
            f"Enabled constraint "
            f"{source_id!r} has no path."
        )

    path = resolve_path(
        project_directory,
        str(raw_path),
    )

    if not path.exists():
        raise RuntimeError(
            f"Constraint source is missing: "
            f"{path}"
        )

    query_geometry = (
        scope_geometry.buffer(
            buffer_m
        )
        if buffer_m > 0
        else scope_geometry
    )

    frame = gpd.read_file(
        path,
        layer=(
            None
            if layer is None
            else str(layer)
        ),
        bbox=query_geometry.bounds,
    )

    if frame.empty:
        return ConstraintResult(
            source_id=source_id,
            label=label,
            enabled=True,
            available=True,
            source_path=path,
            layer=(
                None
                if layer is None
                else str(layer)
            ),
            buffer_m=buffer_m,
            screening_role=(
                screening_role
            ),
            source_feature_count=0,
            geometry=GeometryCollection(),
            checksum=file_sha256(
                path
            ),
        )

    if frame.crs is None:
        raise RuntimeError(
            f"Constraint source has no CRS: "
            f"{path}"
        )

    frame = frame.to_crs(
        target_crs
    )

    frame = (
        repair_invalid_geometries(
            frame,
            name=source_id,
        )
    )

    frame = frame.loc[
        frame.geometry.intersects(
            query_geometry
        )
    ].copy()

    source_feature_count = len(
        frame
    )

    if frame.empty:
        union_geometry = (
            GeometryCollection()
        )

    else:
        clipped = (
            frame.geometry
            .intersection(
                query_geometry
            )
        )

        usable = [
            geometry
            for geometry in clipped
            if (
                geometry is not None
                and not geometry.is_empty
            )
        ]

        if usable:
            union_geometry = union_all(
                usable
            )

            if buffer_m > 0:
                union_geometry = (
                    union_geometry.buffer(
                        buffer_m
                    )
                )

            union_geometry = (
                union_geometry
                .intersection(
                    scope_geometry
                )
            )

            union_geometry = (
                clean_geometry(
                    union_geometry,
                    precision_m,
                )
            )

        else:
            union_geometry = (
                GeometryCollection()
            )

    return ConstraintResult(
        source_id=source_id,
        label=label,
        enabled=True,
        available=True,
        source_path=path,
        layer=(
            None
            if layer is None
            else str(layer)
        ),
        buffer_m=buffer_m,
        screening_role=(
            screening_role
        ),
        source_feature_count=(
            source_feature_count
        ),
        geometry=union_geometry,
        checksum=file_sha256(
            path
        ),
    )


def analyze_parcel_geometries(
    *,
    parcels: gpd.GeoDataFrame,
    scope_geometry: BaseGeometry,
    constraints: dict[
        str,
        BaseGeometry,
    ],
    precision_m: float,
    minimum_component_area_acres: float,
    square_meters_per_acre: float = (
        SQUARE_METERS_PER_ACRE
    ),
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
]:
    minimum_component_area_sq_m = (
        minimum_component_area_acres
        * square_meters_per_acre
    )

    analysis_geometries = [
        clean_geometry(
            parcel_geometry
            .intersection(
                scope_geometry
            ),
            precision_m,
        )
        for parcel_geometry
        in parcels.geometry
    ]

    analysis_series = (
        gpd.GeoSeries(
            analysis_geometries,
            index=parcels.index,
            crs=parcels.crs,
        )
    )

    source_area_columns: dict[
        str,
        pd.Series,
    ] = {}

    for (
        source_id,
        constraint_geometry,
    ) in constraints.items():
        if constraint_geometry.is_empty:
            source_area_columns[
                source_id
            ] = pd.Series(
                0.0,
                index=parcels.index,
                dtype=float,
            )

        else:
            source_area_columns[
                source_id
            ] = (
                analysis_series
                .intersection(
                    constraint_geometry
                )
                .area
                / square_meters_per_acre
            )

    usable_constraints = [
        geometry
        for geometry
        in constraints.values()
        if not geometry.is_empty
    ]

    if usable_constraints:
        total_constraint_union = (
            clean_geometry(
                union_all(
                    usable_constraints
                ),
                precision_m,
            )
        )

    else:
        total_constraint_union = (
            GeometryCollection()
        )

    constrained_geometries = [
        (
            clean_geometry(
                analysis_geometry
                .intersection(
                    total_constraint_union
                ),
                precision_m,
            )
            if not (
                analysis_geometry.is_empty
                or total_constraint_union
                .is_empty
            )
            else GeometryCollection()
        )
        for analysis_geometry
        in analysis_series
    ]

    envelope_geometries = [
        (
            clean_geometry(
                analysis_geometry
                .difference(
                    total_constraint_union
                ),
                precision_m,
            )
            if not (
                analysis_geometry.is_empty
                or total_constraint_union
                .is_empty
            )
            else analysis_geometry
        )
        for analysis_geometry
        in analysis_series
    ]

    largest_geometries = [
        largest_component(
            envelope_geometry,
            minimum_component_area_sq_m,
        )
        for envelope_geometry
        in envelope_geometries
    ]

    analysis_area_acres = (
        analysis_series.area
        / square_meters_per_acre
    )

    constrained_area_acres = (
        gpd.GeoSeries(
            constrained_geometries,
            index=parcels.index,
            crs=parcels.crs,
        ).area
        / square_meters_per_acre
    )

    unconstrained_area_acres = (
        gpd.GeoSeries(
            envelope_geometries,
            index=parcels.index,
            crs=parcels.crs,
        ).area
        / square_meters_per_acre
    )

    largest_area_acres = (
        gpd.GeoSeries(
            largest_geometries,
            index=parcels.index,
            crs=parcels.crs,
        ).area
        / square_meters_per_acre
    )

    component_counts = pd.Series(
        [
            component_count(
                geometry,
                minimum_component_area_sq_m,
            )
            for geometry
            in envelope_geometries
        ],
        index=parcels.index,
        dtype=int,
    )

    unconstrained_fraction = (
        unconstrained_area_acres
        / analysis_area_acres.replace(
            0,
            np.nan,
        )
    ).clip(
        lower=0,
        upper=1,
    )

    largest_contiguous_fraction = (
        largest_area_acres
        / unconstrained_area_acres
        .replace(
            0,
            np.nan,
        )
    ).clip(
        lower=0,
        upper=1,
    )

    raw_constraint_total = (
        sum(
            source_area_columns.values(),
            start=pd.Series(
                0.0,
                index=parcels.index,
                dtype=float,
            ),
        )
    )

    overlapping_constraint_area = (
        raw_constraint_total
        - constrained_area_acres
    ).clip(
        lower=0,
    )

    status = np.select(
        [
            analysis_area_acres.le(0),
            unconstrained_area_acres.le(
                minimum_component_area_acres
            ),
            constrained_area_acres.le(0),
        ],
        [
            "NO_SCOPE_OVERLAP",
            (
                "NO_MAPPED_"
                "UNCONSTRAINED_AREA"
            ),
            (
                "NO_MAPPED_"
                "CONSTRAINT_OVERLAP"
            ),
        ],
        default=(
            "PARTIALLY_CONSTRAINED"
        ),
    )

    constraint_type_values = []

    for index in parcels.index:
        active = [
            source_id
            for source_id, areas
            in source_area_columns.items()
            if float(
                areas.loc[index]
            )
            > 0
        ]

        constraint_type_values.append(
            ";".join(active)
        )

    parcel_analysis = (
        parcels.copy()
    )

    parcel_analysis[
        "analysis_area_acres"
    ] = analysis_area_acres.round(6)

    parcel_analysis[
        "mapped_constrained_area_acres"
    ] = (
        constrained_area_acres.round(
            6
        )
    )

    parcel_analysis[
        "preliminary_unconstrained_area_acres"
    ] = (
        unconstrained_area_acres.round(
            6
        )
    )

    parcel_analysis[
        "preliminary_unconstrained_fraction"
    ] = (
        unconstrained_fraction.round(
            6
        )
    )

    parcel_analysis[
        "largest_contiguous_unconstrained_acres"
    ] = (
        largest_area_acres.round(6)
    )

    parcel_analysis[
        "largest_contiguous_fraction"
    ] = (
        largest_contiguous_fraction
        .round(6)
    )

    parcel_analysis[
        "unconstrained_component_count"
    ] = component_counts

    parcel_analysis[
        "raw_constraint_overlap_acres"
    ] = raw_constraint_total.round(
        6
    )

    parcel_analysis[
        "overlapping_constraint_area_acres"
    ] = (
        overlapping_constraint_area
        .round(6)
    )

    parcel_analysis[
        "mapped_constraint_types"
    ] = constraint_type_values

    parcel_analysis[
        "envelope_status"
    ] = status

    parcel_analysis[
        "preliminary_envelope_only"
    ] = True

    for (
        source_id,
        areas,
    ) in source_area_columns.items():
        parcel_analysis[
            f"{source_id}_overlap_acres"
        ] = areas.round(6)

    envelope_mask = (
        unconstrained_area_acres.gt(
            minimum_component_area_acres
        )
    )

    envelope_attributes = (
        parcel_analysis.loc[
            envelope_mask
        ]
        .drop(
            columns="geometry"
        )
        .copy()
    )

    envelopes = gpd.GeoDataFrame(
        envelope_attributes,
        geometry=[
            envelope_geometries[
                parcels.index.get_loc(
                    index
                )
            ]
            for index
            in envelope_attributes.index
        ],
        crs=parcels.crs,
    )

    largest_mask = (
        largest_area_acres.gt(
            minimum_component_area_acres
        )
    )

    largest_attributes = (
        parcel_analysis.loc[
            largest_mask
        ]
        .drop(
            columns="geometry"
        )
        .copy()
    )

    largest_components = (
        gpd.GeoDataFrame(
            largest_attributes,
            geometry=[
                largest_geometries[
                    parcels.index.get_loc(
                        index
                    )
                ]
                for index
                in largest_attributes.index
            ],
            crs=parcels.crs,
        )
    )

    return (
        gpd.GeoDataFrame(
            parcel_analysis,
            geometry="geometry",
            crs=parcels.crs,
        ),
        envelopes,
        largest_components,
    )


def write_layers(
    *,
    path: Path,
    layers: list[
        tuple[
            str,
            gpd.GeoDataFrame,
        ]
    ],
) -> list[str]:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        path.unlink()

    written_layers: list[str] = []

    for layer_name, frame in layers:
        if frame.empty:
            continue

        frame.to_file(
            path,
            layer=layer_name,
            driver="GPKG",
            index=False,
            mode=(
                "w"
                if not written_layers
                else "a"
            ),
        )

        written_layers.append(
            layer_name
        )

    if not written_layers:
        raise RuntimeError(
            "Envelope pipeline produced "
            "no writable layers."
        )

    return written_layers


def build_scope_envelopes(
    *,
    config_path: Path,
    scope_id: str,
    refresh: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()

    config_path = (
        config_path.resolve()
    )

    config = load_yaml(
        config_path
    )

    project_directory = (
        config_path.parents[2]
    )

    parcel_config_path = (
        resolve_path(
            project_directory,
            config[
                "inputs"
            ][
                "parcel_config"
            ]["path"],
        )
    )

    parcel_config = (
        load_parcel_config(
            parcel_config_path
        )
    )

    parcel_paths = (
        parcel_scope_paths(
            config=parcel_config,
            project_directory=(
                project_directory
            ),
            scope_id=scope_id,
        )
    )

    if not (
        parcel_paths.manifest_output
        .exists()
        and parcel_paths
        .normalized_output.exists()
    ):
        raise RuntimeError(
            "Parcel scope has not been "
            f"built: {scope_id}"
        )

    parcel_manifest = read_json(
        parcel_paths.manifest_output
    )

    paths = envelope_paths(
        config=config,
        project_directory=(
            project_directory
        ),
        scope_id=scope_id,
    )

    config_checksum = file_sha256(
        config_path
    )

    parcel_checksum = file_sha256(
        parcel_paths.normalized_output
    )

    source_checksums: dict[
        str,
        str | None,
    ] = {}

    for source_id in (
        "water",
        "protected_lands",
        "sfha",
        "aviation",
    ):
        source_config = config[
            "inputs"
        ][source_id]

        path_value = source_config.get(
            "path"
        )

        if (
            bool(
                source_config.get(
                    "enabled",
                    False,
                )
            )
            and path_value
        ):
            source_path = resolve_path(
                project_directory,
                str(path_value),
            )

            source_checksums[
                source_id
            ] = (
                file_sha256(
                    source_path
                )
                if source_path.exists()
                else None
            )

        else:
            source_checksums[
                source_id
            ] = None

    if (
        not refresh
        and paths.output.exists()
        and paths.manifest.exists()
    ):
        existing = read_json(
            paths.manifest
        )

        if (
            existing.get(
                "config_checksum"
            )
            == config_checksum
            and existing.get(
                "parcel_scope_checksum"
            )
            == parcel_checksum
            and existing.get(
                "source_checksums"
            )
            == source_checksums
        ):
            print(
                (
                    "[Envelope] Using current "
                    f"scope {scope_id}"
                ),
                flush=True,
            )

            return existing

    target_crs = str(
        config[
            "analysis"
        ][
            "target_crs"
        ]
    )

    precision_m = float(
        config[
            "analysis"
        ][
            "geometry_precision_m"
        ]
    )

    minimum_component_acres = (
        float(
            config[
                "analysis"
            ][
                "minimum_component_area_acres"
            ]
        )
    )

    square_meters_per_acre = (
        float(
            config[
                "analysis"
            ][
                "square_meters_per_acre"
            ]
        )
    )

    print(
        (
            "[Envelope] Loading parcel "
            f"scope {scope_id}"
        ),
        flush=True,
    )

    parcels = gpd.read_file(
        parcel_paths.normalized_output,
        layer="parcels",
    ).to_crs(
        target_crs
    )

    parcels = (
        repair_invalid_geometries(
            parcels,
            name="parcel_envelope_input",
        )
    )

    scope_geometry = (
        scope_geometry_from_manifest(
            parcel_manifest=(
                parcel_manifest
            ),
            parcel_config=(
                parcel_config
            ),
            project_directory=(
                project_directory
            ),
            target_crs=target_crs,
        )
    )

    scope_geometry = (
        clean_geometry(
            scope_geometry,
            precision_m,
        )
    )

    constraint_results: dict[
        str,
        ConstraintResult,
    ] = {}

    for source_id in (
        "water",
        "protected_lands",
        "sfha",
        "aviation",
    ):
        print(
            (
                "[Envelope] Loading "
                f"{source_id}"
            ),
            flush=True,
        )

        constraint_results[
            source_id
        ] = load_constraint(
            source_id=source_id,
            source_config=(
                config[
                    "inputs"
                ][source_id]
            ),
            project_directory=(
                project_directory
            ),
            scope_geometry=(
                scope_geometry
            ),
            target_crs=target_crs,
            precision_m=precision_m,
        )

    constraint_geometries = {
        source_id: result.geometry
        for source_id, result
        in constraint_results.items()
        if result.enabled
    }

    (
        parcel_analysis,
        envelopes,
        largest_components,
    ) = analyze_parcel_geometries(
        parcels=parcels,
        scope_geometry=(
            scope_geometry
        ),
        constraints=(
            constraint_geometries
        ),
        precision_m=precision_m,
        minimum_component_area_acres=(
            minimum_component_acres
        ),
        square_meters_per_acre=(
            square_meters_per_acre
        ),
    )

    constraint_rows = []

    for (
        source_id,
        result,
    ) in constraint_results.items():
        if result.geometry.is_empty:
            continue

        constraint_rows.append(
            {
                "constraint_id": (
                    source_id
                ),
                "label": result.label,
                "buffer_m": (
                    result.buffer_m
                ),
                "screening_role": (
                    result.screening_role
                ),
                "source_feature_count": (
                    result
                    .source_feature_count
                ),
                "geometry": (
                    result.geometry
                ),
            }
        )

    constraints = (
        gpd.GeoDataFrame(
            constraint_rows,
            geometry="geometry",
            crs=target_crs,
        )
        if constraint_rows
        else gpd.GeoDataFrame(
            columns=[
                "constraint_id",
                "geometry",
            ],
            geometry="geometry",
            crs=target_crs,
        )
    )

    written_layers = write_layers(
        path=paths.output,
        layers=[
            (
                "parcel_analysis",
                parcel_analysis,
            ),
            (
                "development_envelopes",
                envelopes,
            ),
            (
                "largest_components",
                largest_components,
            ),
            (
                "scope_constraints",
                constraints,
            ),
        ],
    )

    balance_error = (
        parcel_analysis[
            "analysis_area_acres"
        ]
        - parcel_analysis[
            "mapped_constrained_area_acres"
        ]
        - parcel_analysis[
            "preliminary_unconstrained_area_acres"
        ]
    ).abs()

    status_counts = {
        str(key): int(value)
        for key, value
        in parcel_analysis[
            "envelope_status"
        ].value_counts(
            dropna=False
        ).items()
    }

    constraint_manifest = {
        source_id: {
            "label": result.label,
            "enabled": result.enabled,
            "available": (
                result.available
            ),
            "source_path": (
                None
                if result.source_path
                is None
                else str(
                    result.source_path
                    .relative_to(
                        project_directory
                    )
                )
            ),
            "layer": result.layer,
            "buffer_m": (
                result.buffer_m
            ),
            "screening_role": (
                result.screening_role
            ),
            "source_feature_count": (
                result
                .source_feature_count
            ),
            "scope_constraint_area_acres": (
                round(
                    result.geometry.area
                    / square_meters_per_acre,
                    6,
                )
                if not result.geometry
                .is_empty
                else 0.0
            ),
            "checksum": (
                result.checksum
            ),
        }
        for source_id, result
        in constraint_results.items()
    }

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "parcel_development_envelope"
        ),
        "pipeline_version": (
            config[
                "pipeline_version"
            ]
        ),
        "generated_at_utc": (
            utc_now()
        ),
        "scope_id": scope_id,
        "scope": (
            parcel_manifest[
                "scope"
            ]
        ),
        "counts": {
            "parcel_count": (
                len(parcel_analysis)
            ),
            "envelope_count": (
                len(envelopes)
            ),
            "largest_component_count": (
                len(
                    largest_components
                )
            ),
            "constraint_layer_count": (
                len(constraints)
            ),
        },
        "status_counts": (
            status_counts
        ),
        "constraints": (
            constraint_manifest
        ),
        "statistics": {
            "analysis_area_acres": {
                "total": float(
                    parcel_analysis[
                        "analysis_area_acres"
                    ].sum()
                ),
            },
            "mapped_constrained_area_acres": {
                "total": float(
                    parcel_analysis[
                        "mapped_constrained_area_acres"
                    ].sum()
                ),
            },
            "preliminary_unconstrained_area_acres": {
                "minimum": float(
                    parcel_analysis[
                        "preliminary_unconstrained_area_acres"
                    ].min()
                ),
                "median": float(
                    parcel_analysis[
                        "preliminary_unconstrained_area_acres"
                    ].median()
                ),
                "mean": float(
                    parcel_analysis[
                        "preliminary_unconstrained_area_acres"
                    ].mean()
                ),
                "maximum": float(
                    parcel_analysis[
                        "preliminary_unconstrained_area_acres"
                    ].max()
                ),
                "total": float(
                    parcel_analysis[
                        "preliminary_unconstrained_area_acres"
                    ].sum()
                ),
            },
            "largest_contiguous_unconstrained_acres": {
                "minimum": float(
                    parcel_analysis[
                        "largest_contiguous_unconstrained_acres"
                    ].min()
                ),
                "median": float(
                    parcel_analysis[
                        "largest_contiguous_unconstrained_acres"
                    ].median()
                ),
                "mean": float(
                    parcel_analysis[
                        "largest_contiguous_unconstrained_acres"
                    ].mean()
                ),
                "maximum": float(
                    parcel_analysis[
                        "largest_contiguous_unconstrained_acres"
                    ].max()
                ),
            },
            "maximum_area_balance_error_acres": (
                float(
                    balance_error.max()
                )
            ),
        },
        "safeguards": (
            config["safeguards"]
        ),
        "interpretation": {
            "allowed_term": (
                "Preliminary mapped-constraint "
                "development envelope"
            ),
            "not_allowed_terms": [
                "Buildable area",
                "Approved development area",
                "Construction-ready land",
            ],
            "sfha_buffer_note": (
                "The 91 m SFHA buffer is an "
                "AERIS screening assumption, "
                "not a legal setback."
            ),
        },
        "written_layers": (
            written_layers
        ),
        "config_checksum": (
            config_checksum
        ),
        "parcel_scope_checksum": (
            parcel_checksum
        ),
        "source_checksums": (
            source_checksums
        ),
        "outputs": {
            "geopackage": str(
                paths.output.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "geopackage": (
                file_sha256(
                    paths.output
                )
            ),
        },
        "elapsed_seconds": round(
            time.monotonic()
            - started,
            3,
        ),
    }

    paths.manifest.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    atomic_write_json(
        paths.manifest,
        manifest,
    )

    print(
        (
            "[Envelope] Complete | "
            f"{len(parcel_analysis):,} parcels | "
            f"{len(envelopes):,} envelopes | "
            f"{manifest['elapsed_seconds']:.1f}s"
        ),
        flush=True,
    )

    return manifest
