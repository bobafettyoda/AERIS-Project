from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import yaml
from pyproj import Transformer
from requests.adapters import HTTPAdapter
from shapely.geometry import box
from shapely.ops import unary_union
from urllib3.util.retry import Retry

from analysis.statewide.scoring import (
    inverse_distance_score_series,
    weighted_composite_series,
)
from app.config import (
    SUBSTATIONS_LAYER_URL,
    TRANSMISSION_LINES_LAYER_URL,
)


REGIONAL_ENVELOPES = {
    "western_maryland": (
        -79.50,
        39.15,
        -77.00,
        39.85,
    ),
    "central_maryland": (
        -77.50,
        38.55,
        -76.35,
        39.75,
    ),
    "eastern_maryland": (
        -76.45,
        37.85,
        -74.95,
        39.80,
    ),
}


@dataclass
class SnapshotResult:
    name: str
    layer_url: str
    layer_name: str
    object_id_field: str
    selected_fields: list[str]
    source_object_count: int
    snapshot_feature_count: int
    page_count: int
    output_path: Path
    frame: gpd.GeoDataFrame
    used_cache: bool


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def atomic_write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def load_yaml(
    path: Path,
) -> dict[str, Any]:
    return yaml.safe_load(
        path.read_text(
            encoding="utf-8"
        )
    )


def resolve_path(
    project_directory: Path,
    relative_path: str,
) -> Path:
    return (
        project_directory
        / relative_path
    ).resolve()


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=(
            "GET",
            "POST",
        ),
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": (
                "AERIS/0.2 "
                "grid-infrastructure-pipeline"
            ),
        }
    )

    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    if data is None:
        response = session.get(
            url,
            params={
                "f": "json",
            },
            timeout=180,
        )
    else:
        response = session.post(
            url,
            data=data,
            timeout=180,
        )

    response.raise_for_status()

    payload = response.json()

    if "error" in payload:
        error = payload["error"]

        raise RuntimeError(
            f"{url}: "
            f"{error.get('code')} - "
            f"{error.get('message')}"
        )

    return payload


def chunks(
    values: Sequence[int],
    size: int,
) -> list[list[int]]:
    return [
        list(
            values[
                start : start + size
            ]
        )
        for start in range(
            0,
            len(values),
            size,
        )
    ]


def selected_fields(
    metadata: dict[str, Any],
    desired: Sequence[str],
) -> tuple[str, list[str]]:
    object_id_field = str(
        metadata.get(
            "objectIdField",
        )
        or metadata.get(
            "objectIdFieldName",
        )
        or ""
    )

    if not object_id_field:
        raise RuntimeError(
            "ArcGIS metadata does not identify "
            "an object-ID field."
        )

    available_lookup = {
        str(field["name"]).upper(): (
            str(field["name"])
        )
        for field
        in metadata.get(
            "fields",
            [],
        )
        if field.get("name")
    }

    fields = [
        object_id_field
    ]

    for desired_name in desired:
        actual = available_lookup.get(
            str(desired_name).upper()
        )

        if (
            actual
            and actual not in fields
        ):
            fields.append(actual)

    return (
        object_id_field,
        fields,
    )


def envelope_wgs84(
    geometry,
    source_crs: str,
) -> dict[str, float]:
    min_x, min_y, max_x, max_y = (
        geometry.bounds
    )

    transformer = Transformer.from_crs(
        source_crs,
        "EPSG:4326",
        always_xy=True,
    )

    west, south = transformer.transform(
        min_x,
        min_y,
    )

    east, north = transformer.transform(
        max_x,
        max_y,
    )

    return {
        "xmin": west,
        "ymin": south,
        "xmax": east,
        "ymax": north,
    }


def object_ids_in_envelope(
    session: requests.Session,
    layer_url: str,
    envelope: dict[str, float],
) -> list[int]:
    payload = request_json(
        session,
        f"{layer_url.rstrip('/')}/query",
        data={
            "where": "1=1",
            "geometry": json.dumps(
                {
                    **envelope,
                    "spatialReference": {
                        "wkid": 4326,
                    },
                }
            ),
            "geometryType": (
                "esriGeometryEnvelope"
            ),
            "inSR": "4326",
            "spatialRel": (
                "esriSpatialRelIntersects"
            ),
            "returnIdsOnly": "true",
            "f": "json",
        },
    )

    object_ids = sorted(
        int(value)
        for value
        in (
            payload.get("objectIds")
            or []
        )
    )

    if not object_ids:
        raise RuntimeError(
            "ArcGIS envelope query returned "
            "no object IDs."
        )

    return object_ids


def feature_collection_to_frame(
    features: list[dict[str, Any]],
) -> gpd.GeoDataFrame:
    if not features:
        raise RuntimeError(
            "No ArcGIS features were downloaded."
        )

    frame = (
        gpd.GeoDataFrame.from_features(
            features,
            crs="EPSG:4326",
        )
    )

    frame = frame.loc[
        frame.geometry.notna()
        & ~frame.geometry.is_empty
    ].copy()

    if frame.empty:
        raise RuntimeError(
            "Downloaded features contain "
            "no usable geometry."
        )

    frame.geometry = (
        frame.geometry.make_valid()
    )

    return frame


def regional_counts(
    frame_wgs84: gpd.GeoDataFrame,
) -> dict[str, int]:
    counts = {}

    for region_name, coordinates in (
        REGIONAL_ENVELOPES.items()
    ):
        region = box(
            *coordinates
        )

        counts[region_name] = int(
            frame_wgs84.intersects(
                region
            ).sum()
        )

    return counts


class StageReporter:
    def __init__(
        self,
        total_stages: int,
    ) -> None:
        self.total_stages = total_stages
        self.started_at = time.monotonic()

    def stage(
        self,
        number: int,
        message: str,
    ) -> None:
        elapsed = (
            time.monotonic()
            - self.started_at
        )

        print(
            (
                f"[{number}/{self.total_stages}] "
                f"{message} | "
                f"elapsed {elapsed:,.1f}s"
            ),
            flush=True,
        )

    @staticmethod
    def detail(
        message: str,
    ) -> None:
        print(
            f"      {message}",
            flush=True,
        )


def download_snapshot(
    *,
    name: str,
    session: requests.Session,
    layer_url: str,
    desired_fields: Sequence[str],
    envelope: dict[str, float],
    analysis_buffer,
    target_crs: str,
    output_path: Path,
    output_layer: str,
    page_directory: Path,
    page_size: int,
    refresh: bool,
    resume: bool,
) -> SnapshotResult:
    if refresh:
        output_path.unlink(
            missing_ok=True
        )

        shutil.rmtree(
            page_directory,
            ignore_errors=True,
        )

    metadata = request_json(
        session,
        layer_url,
    )

    (
        object_id_field,
        output_fields,
    ) = selected_fields(
        metadata,
        desired_fields,
    )

    if output_path.exists():
        frame = gpd.read_file(
            output_path,
            layer=output_layer,
        )

        return SnapshotResult(
            name=name,
            layer_url=layer_url,
            layer_name=str(
                metadata.get(
                    "name",
                    name,
                )
            ),
            object_id_field=(
                object_id_field
            ),
            selected_fields=(
                output_fields
            ),
            source_object_count=len(
                frame
            ),
            snapshot_feature_count=len(
                frame
            ),
            page_count=0,
            output_path=output_path,
            frame=frame,
            used_cache=True,
        )

    object_ids = object_ids_in_envelope(
        session,
        layer_url,
        envelope,
    )

    pages = chunks(
        object_ids,
        page_size,
    )

    page_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_features: list[
        dict[str, Any]
    ] = []

    for page_number, page_ids in enumerate(
        pages,
        start=1,
    ):
        page_path = (
            page_directory
            / (
                f"page_{page_number:04d}"
                ".geojson"
            )
        )

        if (
            resume
            and page_path.exists()
        ):
            page_payload = json.loads(
                page_path.read_text(
                    encoding="utf-8"
                )
            )
        else:
            page_payload = request_json(
                session,
                (
                    f"{layer_url.rstrip('/')}"
                    "/query"
                ),
                data={
                    "objectIds": ",".join(
                        str(value)
                        for value
                        in page_ids
                    ),
                    "outFields": ",".join(
                        output_fields
                    ),
                    "returnGeometry": "true",
                    "returnTrueCurves": "false",
                    "outSR": "4326",
                    "f": "geojson",
                },
            )

            atomic_write_json(
                page_path,
                page_payload,
            )

        page_features = (
            page_payload.get(
                "features",
                [],
            )
        )

        all_features.extend(
            page_features
        )

        print(
            (
                f"      [{name}] page "
                f"{page_number:,}/"
                f"{len(pages):,} | "
                f"{len(all_features):,}/"
                f"{len(object_ids):,} features"
            ),
            flush=True,
        )

    if len(all_features) != len(
        object_ids
    ):
        raise RuntimeError(
            f"{name}: requested "
            f"{len(object_ids):,} object IDs "
            f"but received "
            f"{len(all_features):,} features."
        )

    frame_wgs84 = (
        feature_collection_to_frame(
            all_features
        )
    )

    frame_wgs84[
        "_source_object_id"
    ] = frame_wgs84[
        object_id_field
    ]

    frame = frame_wgs84.to_crs(
        target_crs
    )

    frame = gpd.clip(
        frame,
        analysis_buffer,
    )

    frame = frame.loc[
        frame.geometry.notna()
        & ~frame.geometry.is_empty
    ].copy()

    if frame.empty:
        raise RuntimeError(
            f"{name}: no features intersect "
            "the Maryland analysis buffer."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.to_file(
        output_path,
        layer=output_layer,
        driver="GPKG",
        index=False,
    )

    return SnapshotResult(
        name=name,
        layer_url=layer_url,
        layer_name=str(
            metadata.get(
                "name",
                name,
            )
        ),
        object_id_field=(
            object_id_field
        ),
        selected_fields=(
            output_fields
        ),
        source_object_count=len(
            object_ids
        ),
        snapshot_feature_count=len(
            frame
        ),
        page_count=len(pages),
        output_path=output_path,
        frame=frame,
        used_cache=False,
    )


def first_existing_column(
    frame: pd.DataFrame,
    candidates: Sequence[str],
) -> str | None:
    lookup = {
        str(column).upper(): str(column)
        for column in frame.columns
    }

    for candidate in candidates:
        actual = lookup.get(
            candidate.upper()
        )

        if actual:
            return actual

    return None


def nearest_attributes(
    *,
    points: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    prefix: str,
    buffer_m: float,
    desired_attributes: Sequence[str],
) -> pd.DataFrame:
    columns = [
        "_source_object_id",
    ]

    for candidate in desired_attributes:
        actual = first_existing_column(
            features,
            [candidate],
        )

        if (
            actual
            and actual not in columns
        ):
            columns.append(actual)

    feature_subset = features[
        [
            *columns,
            "geometry",
        ]
    ].copy()

    rename_map = {
        column: (
            f"{prefix}_{column.lower()}"
        )
        for column in columns
    }

    feature_subset = (
        feature_subset.rename(
            columns=rename_map
        )
    )

    joined = gpd.sjoin_nearest(
        points[
            [
                "grid_join_index",
                "geometry",
            ]
        ],
        feature_subset,
        how="left",
        max_distance=buffer_m,
        distance_col=(
            f"{prefix}_distance_m"
        ),
    )

    joined = (
        joined.sort_values(
            [
                "grid_join_index",
                f"{prefix}_distance_m",
            ],
            na_position="last",
        )
        .drop_duplicates(
            subset=[
                "grid_join_index",
            ],
            keep="first",
        )
    )

    keep_columns = [
        "grid_join_index",
        f"{prefix}_distance_m",
        *rename_map.values(),
    ]

    return pd.DataFrame(
        joined[
            [
                column
                for column
                in keep_columns
                if column
                in joined.columns
            ]
        ]
    )


def summary_statistics(
    values: pd.Series,
) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "mean": None,
            "maximum": None,
        }

    return {
        "count": int(
            numeric.count()
        ),
        "minimum": round(
            float(numeric.min()),
            3,
        ),
        "median": round(
            float(numeric.median()),
            3,
        ),
        "mean": round(
            float(numeric.mean()),
            3,
        ),
        "maximum": round(
            float(numeric.max()),
            3,
        ),
    }


def run_pipeline(
    config_path: Path,
    *,
    refresh: bool = False,
    resume: bool = False,
    snapshot_only: bool = False,
    score_only: bool = False,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_yaml(
        config_path
    )

    project_directory = (
        config_path.parents[2]
    )

    inputs = config["inputs"]
    outputs = config["outputs"]
    cache = config["cache"]
    snapshot_config = (
        config["snapshot"]
    )

    foundation_grid_path = (
        resolve_path(
            project_directory,
            inputs[
                "foundation_grid"
            ]["path"],
        )
    )

    source_audit_path = (
        resolve_path(
            project_directory,
            inputs[
                "source_audit"
            ]["path"],
        )
    )

    decision_model_path = (
        resolve_path(
            project_directory,
            inputs[
                "decision_model"
            ]["path"],
        )
    )

    if not foundation_grid_path.exists():
        raise RuntimeError(
            "The foundation grid does not exist."
        )

    if not source_audit_path.exists():
        raise RuntimeError(
            "The infrastructure source audit "
            "does not exist."
        )

    audit = json.loads(
        source_audit_path.read_text(
            encoding="utf-8"
        )
    )

    if not audit.get(
        "overall_statewide_candidate"
    ):
        raise RuntimeError(
            "The infrastructure source audit "
            "did not approve statewide use."
        )

    audit_urls = {
        name: source["layer_url"]
        for name, source
        in audit["sources"].items()
    }

    expected_urls = {
        "substations": (
            SUBSTATIONS_LAYER_URL
        ),
        "transmission_lines": (
            TRANSMISSION_LINES_LAYER_URL
        ),
    }

    if audit_urls != expected_urls:
        raise RuntimeError(
            "Infrastructure URLs no longer match "
            "the approved audit."
        )

    target_crs = str(
        snapshot_config["target_crs"]
    )

    buffer_m = float(
        snapshot_config["buffer_m"]
    )

    page_size = int(
        cache["page_size"]
    )

    reporter = StageReporter(
        total_stages=7
    )

    reporter.stage(
        1,
        "Loading foundation grid",
    )

    grid = gpd.read_file(
        foundation_grid_path,
        layer=inputs[
            "foundation_grid"
        ]["layer"],
    ).to_crs(target_crs)

    grid = grid.reset_index(
        drop=True
    )

    grid["grid_join_index"] = (
        grid.index
    )

    state_geometry = unary_union(
        list(grid.geometry)
    )

    analysis_buffer = (
        state_geometry.buffer(
            buffer_m
        )
    )

    query_envelope = envelope_wgs84(
        analysis_buffer,
        target_crs,
    )

    reporter.detail(
        f"{len(grid):,} grid cells"
    )

    reporter.detail(
        (
            f"{buffer_m:,.0f} m "
            "snapshot buffer"
        )
    )

    session = build_session()

    substations_output = resolve_path(
        project_directory,
        outputs[
            "substations"
        ]["path"],
    )

    transmission_output = resolve_path(
        project_directory,
        outputs[
            "transmission_lines"
        ]["path"],
    )

    cache_directory = resolve_path(
        project_directory,
        cache["directory"],
    )

    source_config = config[
        "sources"
    ]

    if score_only:
        if not substations_output.exists():
            raise RuntimeError(
                "Substation snapshot is missing."
            )

        if not transmission_output.exists():
            raise RuntimeError(
                "Transmission snapshot is missing."
            )

    reporter.stage(
        2,
        "Snapshotting Maryland-area substations",
    )

    substations = download_snapshot(
        name="substations",
        session=session,
        layer_url=(
            SUBSTATIONS_LAYER_URL
        ),
        desired_fields=(
            source_config[
                "substations"
            ]["desired_fields"]
        ),
        envelope=query_envelope,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=(
            substations_output
        ),
        output_layer=outputs[
            "substations"
        ]["layer"],
        page_directory=(
            cache_directory
            / "substations"
        ),
        page_size=page_size,
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
    )

    reporter.detail(
        (
            f"{substations.snapshot_feature_count:,} "
            "substations retained"
        )
    )

    reporter.stage(
        3,
        "Snapshotting Maryland-area "
        "transmission lines",
    )

    transmission = download_snapshot(
        name="transmission_lines",
        session=session,
        layer_url=(
            TRANSMISSION_LINES_LAYER_URL
        ),
        desired_fields=(
            source_config[
                "transmission_lines"
            ]["desired_fields"]
        ),
        envelope=query_envelope,
        analysis_buffer=analysis_buffer,
        target_crs=target_crs,
        output_path=(
            transmission_output
        ),
        output_layer=outputs[
            "transmission_lines"
        ]["layer"],
        page_directory=(
            cache_directory
            / "transmission_lines"
        ),
        page_size=page_size,
        refresh=(
            refresh
            and not score_only
        ),
        resume=resume,
    )

    reporter.detail(
        (
            f"{transmission.snapshot_feature_count:,} "
            "transmission features retained"
        )
    )

    if snapshot_only:
        return {
            "snapshot_only": True,
            "substations": (
                substations.snapshot_feature_count
            ),
            "transmission_lines": (
                transmission.snapshot_feature_count
            ),
        }

    model = load_yaml(
        decision_model_path
    )

    preferred = model[
        "preferred_distances"
    ]

    grid_scoring = model[
        "grid_infrastructure_scoring"
    ]

    criterion_weight = float(
        model["criteria"][
            "grid_infrastructure"
        ]["weight"]
    )

    substation_worst_m = float(
        preferred[
            "substation_m"
        ]
    )

    transmission_worst_m = float(
        preferred[
            "transmission_line_m"
        ]
    )

    substation_component_weight = float(
        grid_scoring[
            "substation_component_weight"
        ]
    )

    transmission_component_weight = float(
        grid_scoring[
            "transmission_component_weight"
        ]
    )

    if buffer_m < max(
        substation_worst_m,
        transmission_worst_m,
    ):
        raise RuntimeError(
            "Snapshot buffer is smaller than "
            "a scoring cutoff."
        )

    reporter.stage(
        4,
        "Calculating nearest infrastructure",
    )

    analysis_points = (
        gpd.GeoDataFrame(
            {
                "grid_join_index": (
                    grid[
                        "grid_join_index"
                    ]
                )
            },
            geometry=gpd.points_from_xy(
                grid["analysis_x_m"],
                grid["analysis_y_m"],
            ),
            crs=target_crs,
        )
    )

    substation_join = nearest_attributes(
        points=analysis_points,
        features=substations.frame,
        prefix="substation",
        buffer_m=buffer_m,
        desired_attributes=(
            "NAME",
            "SUB_NAME",
            "SUBNAME",
            "OWNER",
            "STATUS",
            "MAX_VOLT",
            "VOLTAGE",
        ),
    )

    transmission_join = nearest_attributes(
        points=analysis_points,
        features=transmission.frame,
        prefix="transmission",
        buffer_m=buffer_m,
        desired_attributes=(
            "ID",
            "OWNER",
            "STATUS",
            "TYPE",
            "VOLTAGE",
            "VOLT_CLASS",
            "SUB_1",
            "SUB_2",
        ),
    )

    scored_grid = grid.merge(
        substation_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid = scored_grid.merge(
        transmission_join,
        how="left",
        on="grid_join_index",
        validate="one_to_one",
    )

    scored_grid[
        "substation_nearest_status"
    ] = np.where(
        scored_grid[
            "substation_distance_m"
        ].notna(),
        "matched",
        "beyond_snapshot_buffer",
    )

    scored_grid[
        "transmission_nearest_status"
    ] = np.where(
        scored_grid[
            "transmission_distance_m"
        ].notna(),
        "matched",
        "beyond_snapshot_buffer",
    )

    scored_grid[
        "substation_score"
    ] = inverse_distance_score_series(
        scored_grid[
            "substation_distance_m"
        ].fillna(buffer_m),
        best_m=0,
        worst_m=substation_worst_m,
    )

    scored_grid[
        "transmission_score"
    ] = inverse_distance_score_series(
        scored_grid[
            "transmission_distance_m"
        ].fillna(buffer_m),
        best_m=0,
        worst_m=transmission_worst_m,
    )

    scored_grid[
        "grid_infrastructure_score"
    ] = weighted_composite_series(
        [
            (
                scored_grid[
                    "substation_score"
                ],
                substation_component_weight,
            ),
            (
                scored_grid[
                    "transmission_score"
                ],
                transmission_component_weight,
            ),
        ]
    )

    scored_grid[
        "grid_infrastructure_weight"
    ] = criterion_weight

    scored_grid[
        "grid_infrastructure_weighted_contribution"
    ] = (
        scored_grid[
            "grid_infrastructure_score"
        ]
        * criterion_weight
    )

    scored_grid[
        "grid_infrastructure_complete"
    ] = True

    reporter.detail(
        (
            f"{int(scored_grid['substation_distance_m'].notna().sum()):,} "
            "cells matched a substation "
            f"within {buffer_m:,.0f} m"
        )
    )

    reporter.detail(
        (
            f"{int(scored_grid['transmission_distance_m'].notna().sum()):,} "
            "cells matched a transmission line "
            f"within {buffer_m:,.0f} m"
        )
    )

    reporter.stage(
        5,
        "Writing scored statewide grid",
    )

    scored_output = resolve_path(
        project_directory,
        outputs[
            "scored_grid"
        ]["path"],
    )

    scored_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if scored_output.exists():
        scored_output.unlink()

    scored_grid = gpd.GeoDataFrame(
        scored_grid,
        geometry="geometry",
        crs=target_crs,
    )

    scored_grid = scored_grid.drop(
        columns=[
            "grid_join_index",
        ]
    )

    scored_grid.to_file(
        scored_output,
        layer=outputs[
            "scored_grid"
        ]["layer"],
        driver="GPKG",
        index=False,
    )

    reporter.detail(
        str(scored_output)
    )

    reporter.stage(
        6,
        "Writing lightweight point preview",
    )

    preview_output = resolve_path(
        project_directory,
        outputs["preview"]["path"],
    )

    preview_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    preview = gpd.GeoDataFrame(
        scored_grid[
            [
                "cell_id",
                "land_fraction",
                "equity_gate",
                "foundation_screen_ready",
                "population_density_score",
                "substation_distance_m",
                "transmission_distance_m",
                "substation_score",
                "transmission_score",
                "grid_infrastructure_score",
            ]
        ].copy(),
        geometry=gpd.points_from_xy(
            scored_grid["analysis_x_m"],
            scored_grid["analysis_y_m"],
        ),
        crs=target_crs,
    ).to_crs("EPSG:4326")

    if preview_output.exists():
        preview_output.unlink()

    preview.to_file(
        preview_output,
        driver="GeoJSON",
        index=False,
    )

    reporter.detail(
        str(preview_output)
    )

    reporter.stage(
        7,
        "Writing infrastructure manifest",
    )

    known_point = config[
        "known_point_review"
    ]

    known_transformer = (
        Transformer.from_crs(
            "EPSG:4326",
            target_crs,
            always_xy=True,
        )
    )

    known_x, known_y = (
        known_transformer.transform(
            float(
                known_point["longitude"]
            ),
            float(
                known_point["latitude"]
            ),
        )
    )

    point_distance = (
        (
            scored_grid[
                "analysis_x_m"
            ]
            - known_x
        ) ** 2
        + (
            scored_grid[
                "analysis_y_m"
            ]
            - known_y
        ) ** 2
    ) ** 0.5

    known_index = (
        point_distance.idxmin()
    )

    known_cell = scored_grid.loc[
        known_index
    ]

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_grid_infrastructure"
        ),
        "generated_at_utc": utc_now(),
        "snapshot_label": config[
            "snapshot_label"
        ],
        "source_audit": {
            "path": str(
                source_audit_path.relative_to(
                    project_directory
                )
            ),
            "sha256": file_sha256(
                source_audit_path
            ),
            "decision": audit[
                "decision"
            ],
        },
        "snapshot": {
            "target_crs": target_crs,
            "buffer_m": buffer_m,
            "query_envelope_wgs84": (
                query_envelope
            ),
        },
        "sources": {
            "substations": {
                "layer_url": (
                    substations.layer_url
                ),
                "layer_name": (
                    substations.layer_name
                ),
                "object_id_field": (
                    substations.object_id_field
                ),
                "selected_fields": (
                    substations.selected_fields
                ),
                "source_object_count": (
                    substations.source_object_count
                ),
                "snapshot_feature_count": (
                    substations.snapshot_feature_count
                ),
                "used_cache": (
                    substations.used_cache
                ),
                "sha256": file_sha256(
                    substations.output_path
                ),
                "regional_feature_counts": (
                    regional_counts(
                        substations.frame.to_crs(
                            "EPSG:4326"
                        )
                    )
                ),
            },
            "transmission_lines": {
                "layer_url": (
                    transmission.layer_url
                ),
                "layer_name": (
                    transmission.layer_name
                ),
                "object_id_field": (
                    transmission.object_id_field
                ),
                "selected_fields": (
                    transmission.selected_fields
                ),
                "source_object_count": (
                    transmission.source_object_count
                ),
                "snapshot_feature_count": (
                    transmission.snapshot_feature_count
                ),
                "used_cache": (
                    transmission.used_cache
                ),
                "sha256": file_sha256(
                    transmission.output_path
                ),
                "regional_feature_counts": (
                    regional_counts(
                        transmission.frame.to_crs(
                            "EPSG:4326"
                        )
                    )
                ),
            },
        },
        "scoring": {
            "criterion": (
                "grid_infrastructure"
            ),
            "criterion_weight": (
                criterion_weight
            ),
            "substation": {
                "best_m": 0,
                "worst_m": (
                    substation_worst_m
                ),
                "component_weight": (
                    substation_component_weight
                ),
            },
            "transmission_lines": {
                "best_m": 0,
                "worst_m": (
                    transmission_worst_m
                ),
                "component_weight": (
                    transmission_component_weight
                ),
            },
        },
        "grid": {
            "cell_count": len(
                scored_grid
            ),
            "substation_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "substation_distance_m"
                    ]
                )
            ),
            "transmission_distance_statistics_m": (
                summary_statistics(
                    scored_grid[
                        "transmission_distance_m"
                    ]
                )
            ),
            "grid_score_statistics": (
                summary_statistics(
                    scored_grid[
                        "grid_infrastructure_score"
                    ]
                )
            ),
            "cells_with_substation_within_cutoff": (
                int(
                    scored_grid[
                        "substation_distance_m"
                    ].le(
                        substation_worst_m
                    ).sum()
                )
            ),
            "cells_with_transmission_within_cutoff": (
                int(
                    scored_grid[
                        "transmission_distance_m"
                    ].le(
                        transmission_worst_m
                    ).sum()
                )
            ),
            "complete_cells": int(
                scored_grid[
                    "grid_infrastructure_complete"
                ].sum()
            ),
        },
        "known_point_review": {
            "input_latitude": (
                known_point["latitude"]
            ),
            "input_longitude": (
                known_point["longitude"]
            ),
            "nearest_grid_cell": (
                known_cell["cell_id"]
            ),
            "representative_point_distance_m": (
                round(
                    float(
                        point_distance.loc[
                            known_index
                        ]
                    ),
                    3,
                )
            ),
            "grid_cell_substation_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "substation_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "substation_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "grid_cell_transmission_distance_m": (
                None
                if pd.isna(
                    known_cell[
                        "transmission_distance_m"
                    ]
                )
                else round(
                    float(
                        known_cell[
                            "transmission_distance_m"
                        ]
                    ),
                    3,
                )
            ),
            "grid_cell_score": round(
                float(
                    known_cell[
                        "grid_infrastructure_score"
                    ]
                ),
                6,
            ),
            "point_evaluator_score": (
                known_point[
                    "point_evaluator_score"
                ]
            ),
            "note": (
                "The grid representative point "
                "is not expected to exactly match "
                "the original clicked coordinate."
            ),
        },
        "outputs": {
            "substations": str(
                substations_output.relative_to(
                    project_directory
                )
            ),
            "transmission_lines": str(
                transmission_output.relative_to(
                    project_directory
                )
            ),
            "scored_grid": str(
                scored_output.relative_to(
                    project_directory
                )
            ),
            "preview": str(
                preview_output.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "scored_grid": file_sha256(
                scored_output
            ),
            "preview": file_sha256(
                preview_output
            ),
        },
    }

    manifest_output = resolve_path(
        project_directory,
        outputs["manifest"]["path"],
    )

    atomic_write_json(
        manifest_output,
        manifest,
    )

    reporter.detail(
        str(manifest_output)
    )

    return manifest
