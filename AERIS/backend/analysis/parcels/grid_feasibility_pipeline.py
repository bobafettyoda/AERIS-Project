from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import yaml
from shapely import LineString, make_valid, union_all
from shapely.ops import nearest_points

from analysis.parcels.pipeline import (
    file_sha256,
    load_config as load_parcel_config,
    parcel_scope_paths,
    read_json,
    resolve_path,
)
from analysis.statewide.grid_infrastructure_pipeline import (
    atomic_write_json,
    repair_invalid_geometries,
)


@dataclass(frozen=True)
class GridFeasibilityPaths:
    output: Path
    manifest: Path


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


def grid_feasibility_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
    scope_id: str,
) -> GridFeasibilityPaths:
    output_root = resolve_path(
        project_directory,
        config[
            "outputs"
        ]["derived_directory"]["path"],
    )

    manifest_root = resolve_path(
        project_directory,
        config[
            "outputs"
        ]["manifest_directory"]["path"],
    )

    return GridFeasibilityPaths(
        output=(
            output_root
            / f"{scope_id}.gpkg"
        ),
        manifest=(
            manifest_root
            / f"{scope_id}.json"
        ),
    )


def first_layer(
    path: Path,
    configured_layer: str | None,
) -> str:
    layers = [
        str(row[0])
        for row
        in pyogrio.list_layers(path)
    ]

    if not layers:
        raise RuntimeError(
            f"No layers found in {path}"
        )

    if configured_layer:
        if configured_layer not in layers:
            raise RuntimeError(
                f"Layer {configured_layer!r} "
                f"was not found in {path}. "
                f"Available layers: {layers}"
            )

        return configured_layer

    return layers[0]


def find_column(
    frame: pd.DataFrame,
    *candidates: str,
) -> str | None:
    lookup = {
        str(column).casefold(): str(
            column
        )
        for column in frame.columns
    }

    for candidate in candidates:
        actual = lookup.get(
            candidate.casefold()
        )

        if actual is not None:
            return actual

    return None


def text_series(
    frame: pd.DataFrame,
    *candidates: str,
) -> pd.Series:
    actual = find_column(
        frame,
        *candidates,
    )

    if actual is None:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
        frame[actual]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def numeric_series(
    frame: pd.DataFrame,
    *candidates: str,
) -> pd.Series:
    result = pd.Series(
        np.nan,
        index=frame.index,
        dtype=float,
    )

    for candidate in candidates:
        actual = find_column(
            frame,
            candidate,
        )

        if actual is None:
            continue

        candidate_values = pd.to_numeric(
            frame[actual],
            errors="coerce",
        )

        result = result.where(
            result.notna(),
            candidate_values,
        )

    return result


def clean_voltage(
    values: pd.Series,
) -> pd.Series:
    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    return numeric.where(
        numeric.gt(0)
        & numeric.le(1000)
    )


def voltage_class(
    value: Any,
    voltage_config: dict[str, Any],
) -> str:
    try:
        numeric = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return "UNKNOWN"

    if not np.isfinite(numeric):
        return "UNKNOWN"

    if numeric >= float(
        voltage_config[
            "extra_high_minimum_kv"
        ]
    ):
        return "EXTRA_HIGH_345_KV_PLUS"

    if numeric >= float(
        voltage_config[
            "high_minimum_kv"
        ]
    ):
        return "HIGH_230_TO_344_KV"

    if numeric >= float(
        voltage_config[
            "regional_minimum_kv"
        ]
    ):
        return "REGIONAL_115_TO_229_KV"

    if numeric >= float(
        voltage_config[
            "subtransmission_minimum_kv"
        ]
    ):
        return "SUBTRANSMISSION_69_TO_114_KV"

    if numeric > 0:
        return "BELOW_69_KV"

    return "UNKNOWN"


def inferred_flag(
    values: pd.Series,
) -> pd.Series:
    normalized = (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
    )

    return normalized.isin(
        {
            "1",
            "true",
            "t",
            "yes",
            "y",
            "inferred",
        }
    )


def source_date_series(
    frame: pd.DataFrame,
    *candidates: str,
) -> pd.Series:
    actual = find_column(
        frame,
        *candidates,
    )

    if actual is None:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    values = frame[actual]

    if pd.api.types.is_datetime64_any_dtype(
        values
    ):
        return (
            values.dt.strftime(
                "%Y-%m-%d"
            )
            .astype("string")
            .fillna("")
        )

    return (
        values.astype("string")
        .fillna("")
        .str.strip()
    )


def normalize_transmission_lines(
    frame: gpd.GeoDataFrame,
    *,
    voltage_config: dict[str, Any],
) -> gpd.GeoDataFrame:
    result = frame.copy()

    feature_id = text_series(
        result,
        "ID",
        "OBJECTID_1",
        "OBJECTID",
    )

    feature_id = feature_id.where(
        feature_id.ne(""),
        pd.Series(
            [
                f"TRANSMISSION-{index}"
                for index in range(
                    len(result)
                )
            ],
            index=result.index,
            dtype="string",
        ),
    )

    voltage = clean_voltage(
        numeric_series(
            result,
            "VOLTAGE",
        )
    )

    raw_inferred = text_series(
        result,
        "INFERRED",
    )

    inferred = inferred_flag(
        raw_inferred
    )

    data_confidence = np.select(
        [
            voltage.notna()
            & ~inferred,
            voltage.notna(),
        ],
        [
            "HIGH",
            "MEDIUM",
        ],
        default="LOW",
    )

    normalized = gpd.GeoDataFrame(
        {
            "evidence_kind": (
                "TRANSMISSION_LINE"
            ),
            "grid_feature_id": (
                feature_id
            ),
            "transmission_id": (
                feature_id
            ),
            "transmission_type": (
                text_series(
                    result,
                    "TYPE",
                )
            ),
            "transmission_status": (
                text_series(
                    result,
                    "STATUS",
                )
            ),
            "transmission_owner": (
                text_series(
                    result,
                    "OWNER",
                )
            ),
            "transmission_voltage_kv": (
                voltage
            ),
            "transmission_voltage_class_source": (
                text_series(
                    result,
                    "VOLT_CLASS",
                )
            ),
            "transmission_voltage_class": [
                voltage_class(
                    value,
                    voltage_config,
                )
                for value in voltage
            ],
            "transmission_inferred": (
                inferred
            ),
            "transmission_inferred_source_value": (
                raw_inferred
            ),
            "transmission_substation_1": (
                text_series(
                    result,
                    "SUB_1",
                )
            ),
            "transmission_substation_2": (
                text_series(
                    result,
                    "SUB_2",
                )
            ),
            "transmission_source": (
                text_series(
                    result,
                    "SOURCE",
                )
            ),
            "transmission_source_date": (
                source_date_series(
                    result,
                    "SOURCEDATE",
                )
            ),
            "transmission_validation_method": (
                text_series(
                    result,
                    "VAL_METHOD",
                )
            ),
            "transmission_validation_date": (
                source_date_series(
                    result,
                    "VAL_DATE",
                )
            ),
            "transmission_data_confidence": (
                data_confidence
            ),
        },
        geometry=result.geometry,
        crs=result.crs,
    )

    return normalized.drop_duplicates(
        subset=[
            "grid_feature_id",
        ]
    ).reset_index(drop=True)


def normalize_substations(
    frame: gpd.GeoDataFrame,
    *,
    voltage_config: dict[str, Any],
) -> gpd.GeoDataFrame:
    result = frame.copy()

    feature_id = text_series(
        result,
        "ID",
        "OBJECTID_1",
        "OBJECTID",
    )

    feature_id = feature_id.where(
        feature_id.ne(""),
        pd.Series(
            [
                f"SUBSTATION-{index}"
                for index in range(
                    len(result)
                )
            ],
            index=result.index,
            dtype="string",
        ),
    )

    maximum_voltage = clean_voltage(
        numeric_series(
            result,
            "MAX_VOLT",
        )
    )

    minimum_voltage = clean_voltage(
        numeric_series(
            result,
            "MIN_VOLT",
        )
    )

    maximum_inferred_raw = (
        text_series(
            result,
            "MAX_INFER",
        )
    )

    minimum_inferred_raw = (
        text_series(
            result,
            "MIN_INFER",
        )
    )

    maximum_inferred = (
        inferred_flag(
            maximum_inferred_raw
        )
    )

    minimum_inferred = (
        inferred_flag(
            minimum_inferred_raw
        )
    )

    inferred_any = (
        maximum_inferred
        | minimum_inferred
    )

    data_confidence = np.select(
        [
            maximum_voltage.notna()
            & ~inferred_any,
            maximum_voltage.notna(),
        ],
        [
            "HIGH",
            "MEDIUM",
        ],
        default="LOW",
    )

    normalized = gpd.GeoDataFrame(
        {
            "evidence_kind": (
                "SUBSTATION"
            ),
            "grid_feature_id": (
                feature_id
            ),
            "substation_id": (
                feature_id
            ),
            "substation_name": (
                text_series(
                    result,
                    "NAME",
                )
            ),
            "substation_type": (
                text_series(
                    result,
                    "TYPE",
                )
            ),
            "substation_status": (
                text_series(
                    result,
                    "STATUS",
                )
            ),
            "substation_city": (
                text_series(
                    result,
                    "CITY",
                )
            ),
            "substation_county": (
                text_series(
                    result,
                    "COUNTY",
                )
            ),
            "substation_line_count": (
                numeric_series(
                    result,
                    "LINES",
                )
            ),
            "substation_max_voltage_kv": (
                maximum_voltage
            ),
            "substation_min_voltage_kv": (
                minimum_voltage
            ),
            "substation_voltage_class": [
                voltage_class(
                    value,
                    voltage_config,
                )
                for value
                in maximum_voltage
            ],
            "substation_max_voltage_inferred": (
                maximum_inferred
            ),
            "substation_min_voltage_inferred": (
                minimum_inferred
            ),
            "substation_source": (
                text_series(
                    result,
                    "SOURCE",
                )
            ),
            "substation_source_date": (
                source_date_series(
                    result,
                    "SOURCEDATE",
                )
            ),
            "substation_validation_method": (
                text_series(
                    result,
                    "VAL_METHOD",
                )
            ),
            "substation_validation_date": (
                source_date_series(
                    result,
                    "VAL_DATE",
                )
            ),
            "substation_data_confidence": (
                data_confidence
            ),
        },
        geometry=result.geometry,
        crs=result.crs,
    )

    return normalized.drop_duplicates(
        subset=[
            "grid_feature_id",
        ]
    ).reset_index(drop=True)


def derive_grid_context_class(
    *,
    transmission_distance_m: Any,
    transmission_voltage_kv: Any,
    substation_distance_m: Any,
    substation_voltage_kv: Any,
    maximum_nearby_voltage_kv: Any,
    context_config: dict[str, Any],
) -> str:
    def number(
        value: Any,
    ) -> float | None:
        try:
            result = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not np.isfinite(result):
            return None

        return result

    line_distance = number(
        transmission_distance_m
    )

    line_voltage = number(
        transmission_voltage_kv
    )

    station_distance = number(
        substation_distance_m
    )

    station_voltage = number(
        substation_voltage_kv
    )

    nearby_voltage = number(
        maximum_nearby_voltage_kv
    )

    if (
        line_distance is None
        and station_distance is None
    ):
        return "INSUFFICIENT_MAPPED_GRID_DATA"

    very_strong = context_config[
        "very_strong"
    ]

    effective_line_voltage = max(
        [
            value
            for value in (
                line_voltage,
                nearby_voltage,
            )
            if value is not None
        ],
        default=None,
    )

    if (
        line_distance is not None
        and line_distance
        <= float(
            very_strong[
                "transmission_distance_m"
            ]
        )
        and effective_line_voltage
        is not None
        and effective_line_voltage
        >= float(
            very_strong[
                "transmission_voltage_kv"
            ]
        )
        and station_distance
        is not None
        and station_distance
        <= float(
            very_strong[
                "substation_distance_m"
            ]
        )
        and station_voltage
        is not None
        and station_voltage
        >= float(
            very_strong[
                "substation_voltage_kv"
            ]
        )
    ):
        return "VERY_STRONG_MAPPED_GRID_CONTEXT"

    strong = context_config[
        "strong"
    ]

    if (
        line_distance is not None
        and line_distance
        <= float(
            strong[
                "transmission_distance_m"
            ]
        )
        and effective_line_voltage
        is not None
        and effective_line_voltage
        >= float(
            strong[
                "transmission_voltage_kv"
            ]
        )
        and station_distance
        is not None
        and station_distance
        <= float(
            strong[
                "substation_distance_m"
            ]
        )
    ):
        return "STRONG_MAPPED_GRID_CONTEXT"

    moderate = context_config[
        "moderate"
    ]

    if (
        (
            line_distance is not None
            and line_distance
            <= float(
                moderate[
                    "transmission_distance_m"
                ]
            )
        )
        or (
            station_distance is not None
            and station_distance
            <= float(
                moderate[
                    "substation_distance_m"
                ]
            )
        )
    ):
        return "MODERATE_MAPPED_GRID_CONTEXT"

    return "LIMITED_MAPPED_GRID_CONTEXT"


def nearest_matches(
    *,
    parcels: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    maximum_distance_m: float,
    voltage_column: str,
) -> gpd.GeoDataFrame:
    left = parcels[
        [
            "_parcel_index",
            "parcel_id",
            "geometry",
        ]
    ].copy()

    right = features.copy()

    joined = gpd.sjoin_nearest(
        left,
        right,
        how="left",
        max_distance=(
            maximum_distance_m
        ),
        distance_col=(
            "_nearest_distance_m"
        ),
    )

    if voltage_column in joined:
        joined[
            "_voltage_sort"
        ] = pd.to_numeric(
            joined[
                voltage_column
            ],
            errors="coerce",
        ).fillna(-1)

    else:
        joined[
            "_voltage_sort"
        ] = -1.0

    return (
        joined.sort_values(
            [
                "_parcel_index",
                "_nearest_distance_m",
                "_voltage_sort",
            ],
            ascending=[
                True,
                True,
                False,
            ],
            na_position="last",
        )
        .drop_duplicates(
            subset=[
                "_parcel_index",
            ],
            keep="first",
        )
    )


def radius_summary(
    *,
    parcels: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    radius_m: float,
    voltage_column: str,
    owner_column: str | None,
    prefix: str,
) -> pd.DataFrame:
    buffers = gpd.GeoDataFrame(
        {
            "_parcel_index": (
                parcels[
                    "_parcel_index"
                ]
            )
        },
        geometry=(
            parcels.geometry.buffer(
                radius_m
            )
        ),
        crs=parcels.crs,
    )

    fields = [
        "grid_feature_id",
        voltage_column,
        "geometry",
    ]

    if (
        owner_column
        and owner_column
        in features.columns
    ):
        fields.insert(
            -1,
            owner_column,
        )

    joined = gpd.sjoin(
        buffers,
        features[fields],
        how="left",
        predicate="intersects",
    )

    matched = joined.loc[
        joined[
            "index_right"
        ].notna()
    ].copy()

    result = pd.DataFrame(
        {
            "_parcel_index": (
                parcels[
                    "_parcel_index"
                ]
            )
        }
    )

    result[
        f"{prefix}_feature_count"
    ] = 0

    result[
        f"{prefix}_known_voltage_count"
    ] = 0

    result[
        f"{prefix}_maximum_voltage_kv"
    ] = np.nan

    result[
        f"{prefix}_distinct_owner_count"
    ] = 0

    result[
        f"{prefix}_owners"
    ] = ""

    if matched.empty:
        return result

    matched[
        "_numeric_voltage"
    ] = pd.to_numeric(
        matched[
            voltage_column
        ],
        errors="coerce",
    )

    grouped = matched.groupby(
        "_parcel_index",
        sort=False,
    )

    feature_count = grouped[
        "grid_feature_id"
    ].nunique()

    known_voltage_count = (
        grouped[
            "_numeric_voltage"
        ].count()
    )

    maximum_voltage = (
        grouped[
            "_numeric_voltage"
        ].max()
    )

    result = result.set_index(
        "_parcel_index"
    )

    result.loc[
        feature_count.index,
        f"{prefix}_feature_count",
    ] = feature_count.astype(int)

    result.loc[
        known_voltage_count.index,
        f"{prefix}_known_voltage_count",
    ] = known_voltage_count.astype(int)

    result.loc[
        maximum_voltage.index,
        f"{prefix}_maximum_voltage_kv",
    ] = maximum_voltage

    if (
        owner_column
        and owner_column
        in matched.columns
    ):
        owner_values = (
            matched[
                owner_column
            ]
            .astype("string")
            .fillna("")
            .str.strip()
        )

        matched[
            "_normalized_owner"
        ] = owner_values

        owner_groups = (
            matched.loc[
                owner_values.ne("")
            ]
            .groupby(
                "_parcel_index"
            )[
                "_normalized_owner"
            ]
        )

        owner_count = (
            owner_groups.nunique()
        )

        owner_list = owner_groups.apply(
            lambda values: "; ".join(
                sorted(
                    set(
                        str(value)
                        for value
                        in values
                        if str(value)
                    )
                )[:10]
            )
        )

        result.loc[
            owner_count.index,
            f"{prefix}_distinct_owner_count",
        ] = owner_count.astype(int)

        result.loc[
            owner_list.index,
            f"{prefix}_owners",
        ] = owner_list

    return result.reset_index()


def connector_frame(
    *,
    parcels: gpd.GeoDataFrame,
    matches: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    evidence_kind: str,
    minimum_length_m: float,
) -> gpd.GeoDataFrame:
    records: list[
        dict[str, Any]
    ] = []

    for _, row in matches.iterrows():
        right_index = row.get(
            "index_right"
        )

        if pd.isna(right_index):
            continue

        parcel_index = int(
            row["_parcel_index"]
        )

        feature_index = int(
            right_index
        )

        parcel_geometry = (
            parcels.loc[
                parcels[
                    "_parcel_index"
                ].eq(parcel_index)
            ].geometry.iloc[0]
        )

        feature_geometry = (
            features.geometry.loc[
                feature_index
            ]
        )

        parcel_point, feature_point = (
            nearest_points(
                parcel_geometry,
                feature_geometry,
            )
        )

        length_m = float(
            parcel_point.distance(
                feature_point
            )
        )

        if length_m < minimum_length_m:
            continue

        records.append(
            {
                "evidence_kind": (
                    evidence_kind
                ),
                "parcel_id": str(
                    row["parcel_id"]
                ),
                "grid_feature_id": str(
                    row.get(
                        "grid_feature_id",
                        "",
                    )
                ),
                "distance_m": (
                    round(
                        length_m,
                        3,
                    )
                ),
                "geometry": LineString(
                    [
                        parcel_point,
                        feature_point,
                    ]
                ),
            }
        )

    if not records:
        return gpd.GeoDataFrame(
            columns=[
                "evidence_kind",
                "parcel_id",
                "grid_feature_id",
                "distance_m",
                "geometry",
            ],
            geometry="geometry",
            crs=parcels.crs,
        )

    return gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs=parcels.crs,
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

    written: list[str] = []

    for layer_name, frame in layers:
        if frame.empty:
            continue

        frame.to_file(
            path,
            layer=layer_name,
            driver="GPKG",
            mode=(
                "w"
                if not written
                else "a"
            ),
            index=False,
        )

        written.append(
            layer_name
        )

    if not written:
        raise RuntimeError(
            "Grid-feasibility pipeline "
            "produced no writable layers."
        )

    return written


def build_grid_feasibility(
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

    parcel_config_path = resolve_path(
        project_directory,
        config[
            "inputs"
        ]["parcel_config"]["path"],
    )

    parcel_config = (
        load_parcel_config(
            parcel_config_path
        )
    )

    parcel_paths = parcel_scope_paths(
        config=parcel_config,
        project_directory=(
            project_directory
        ),
        scope_id=scope_id,
    )

    if not (
        parcel_paths.normalized_output
        .exists()
        and parcel_paths.manifest_output
        .exists()
    ):
        raise RuntimeError(
            "Parcel scope has not been "
            f"built: {scope_id}"
        )

    paths = grid_feasibility_paths(
        config=config,
        project_directory=(
            project_directory
        ),
        scope_id=scope_id,
    )

    transmission_config = (
        config[
            "inputs"
        ]["transmission_lines"]
    )

    substation_config = (
        config[
            "inputs"
        ]["substations"]
    )

    transmission_path = resolve_path(
        project_directory,
        transmission_config["path"],
    )

    substation_path = resolve_path(
        project_directory,
        substation_config["path"],
    )

    for source_path in (
        transmission_path,
        substation_path,
    ):
        if not source_path.exists():
            raise RuntimeError(
                "Grid source is missing: "
                f"{source_path}"
            )

    config_checksum = file_sha256(
        config_path
    )

    parcel_checksum = file_sha256(
        parcel_paths.normalized_output
    )

    transmission_checksum = (
        file_sha256(
            transmission_path
        )
    )

    substation_checksum = (
        file_sha256(
            substation_path
        )
    )

    source_checksums = {
        "transmission_lines": (
            transmission_checksum
        ),
        "substations": (
            substation_checksum
        ),
    }

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
                    "[Grid feasibility] "
                    "Using current scope "
                    f"{scope_id}"
                ),
                flush=True,
            )

            return existing

    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    print(
        (
            "[Grid feasibility] Loading "
            f"parcel scope {scope_id}"
        ),
        flush=True,
    )

    parcels = gpd.read_file(
        parcel_paths.normalized_output,
        layer="parcels",
    ).to_crs(
        target_crs
    )

    parcels = repair_invalid_geometries(
        parcels,
        name=(
            "grid_feasibility_parcels"
        ),
    ).reset_index(drop=True)

    parcels[
        "_parcel_index"
    ] = parcels.index

    scope_geometry = union_all(
        list(parcels.geometry)
    )

    if not scope_geometry.is_valid:
        scope_geometry = make_valid(
            scope_geometry
        )

    scope_buffer = (
        scope_geometry.buffer(
            float(
                config[
                    "analysis"
                ][
                    "scope_buffer_m"
                ]
            )
        )
    )

    voltage_config = (
        config[
            "analysis"
        ]["voltage_classes"]
    )

    transmission_layer = first_layer(
        transmission_path,
        transmission_config.get(
            "layer"
        ),
    )

    substation_layer = first_layer(
        substation_path,
        substation_config.get(
            "layer"
        ),
    )

    transmission_source = (
        gpd.read_file(
            transmission_path,
            layer=transmission_layer,
        )
        .to_crs(target_crs)
    )

    substation_source = (
        gpd.read_file(
            substation_path,
            layer=substation_layer,
        )
        .to_crs(target_crs)
    )

    transmission_source = (
        repair_invalid_geometries(
            transmission_source,
            name="transmission_lines",
        )
    )

    substation_source = (
        repair_invalid_geometries(
            substation_source,
            name="substations",
        )
    )

    transmission_source = (
        transmission_source.loc[
            transmission_source
            .geometry.intersects(
                scope_buffer
            )
        ].copy()
    )

    substation_source = (
        substation_source.loc[
            substation_source
            .geometry.intersects(
                scope_buffer
            )
        ].copy()
    )

    if transmission_source.empty:
        raise RuntimeError(
            "No mapped transmission lines "
            "were found near the parcel scope."
        )

    if substation_source.empty:
        raise RuntimeError(
            "No mapped substations were "
            "found near the parcel scope."
        )

    transmission = (
        normalize_transmission_lines(
            transmission_source,
            voltage_config=(
                voltage_config
            ),
        )
    )

    substations = (
        normalize_substations(
            substation_source,
            voltage_config=(
                voltage_config
            ),
        )
    )

    print(
        (
            "[Grid feasibility] "
            f"{len(transmission):,} "
            "transmission features and "
            f"{len(substations):,} "
            "substations in scope buffer"
        ),
        flush=True,
    )

    maximum_distance = float(
        config[
            "analysis"
        ][
            "maximum_nearest_distance_m"
        ]
    )

    nearest_transmission = (
        nearest_matches(
            parcels=parcels,
            features=transmission,
            maximum_distance_m=(
                maximum_distance
            ),
            voltage_column=(
                "transmission_voltage_kv"
            ),
        )
    )

    nearest_substation = (
        nearest_matches(
            parcels=parcels,
            features=substations,
            maximum_distance_m=(
                maximum_distance
            ),
            voltage_column=(
                "substation_max_voltage_kv"
            ),
        )
    )

    transmission_attributes = [
        "_parcel_index",
        "_nearest_distance_m",
        "grid_feature_id",
        "transmission_id",
        "transmission_type",
        "transmission_status",
        "transmission_owner",
        "transmission_voltage_kv",
        "transmission_voltage_class_source",
        "transmission_voltage_class",
        "transmission_inferred",
        "transmission_substation_1",
        "transmission_substation_2",
        "transmission_source_date",
        "transmission_validation_method",
        "transmission_validation_date",
        "transmission_data_confidence",
    ]

    transmission_attributes = [
        column
        for column
        in transmission_attributes
        if column
        in nearest_transmission.columns
    ]

    transmission_context = (
        nearest_transmission[
            transmission_attributes
        ].copy()
    )

    transmission_context = (
        transmission_context.rename(
            columns={
                "_nearest_distance_m": (
                    "nearest_transmission_distance_m"
                ),
                "grid_feature_id": (
                    "nearest_transmission_feature_id"
                ),
                "transmission_id": (
                    "nearest_transmission_id"
                ),
                "transmission_type": (
                    "nearest_transmission_type"
                ),
                "transmission_status": (
                    "nearest_transmission_status"
                ),
                "transmission_owner": (
                    "nearest_transmission_owner"
                ),
                "transmission_voltage_kv": (
                    "nearest_transmission_voltage_kv"
                ),
                "transmission_voltage_class_source": (
                    "nearest_transmission_voltage_class_source"
                ),
                "transmission_voltage_class": (
                    "nearest_transmission_voltage_class"
                ),
                "transmission_inferred": (
                    "nearest_transmission_inferred"
                ),
                "transmission_substation_1": (
                    "nearest_transmission_substation_1"
                ),
                "transmission_substation_2": (
                    "nearest_transmission_substation_2"
                ),
                "transmission_source_date": (
                    "nearest_transmission_source_date"
                ),
                "transmission_validation_method": (
                    "nearest_transmission_validation_method"
                ),
                "transmission_validation_date": (
                    "nearest_transmission_validation_date"
                ),
                "transmission_data_confidence": (
                    "nearest_transmission_data_confidence"
                ),
            }
        )
    )

    substation_attributes = [
        "_parcel_index",
        "_nearest_distance_m",
        "grid_feature_id",
        "substation_id",
        "substation_name",
        "substation_type",
        "substation_status",
        "substation_city",
        "substation_county",
        "substation_line_count",
        "substation_max_voltage_kv",
        "substation_min_voltage_kv",
        "substation_voltage_class",
        "substation_max_voltage_inferred",
        "substation_min_voltage_inferred",
        "substation_source_date",
        "substation_validation_method",
        "substation_validation_date",
        "substation_data_confidence",
    ]

    substation_attributes = [
        column
        for column
        in substation_attributes
        if column
        in nearest_substation.columns
    ]

    substation_context = (
        nearest_substation[
            substation_attributes
        ].copy()
    )

    substation_context = (
        substation_context.rename(
            columns={
                "_nearest_distance_m": (
                    "nearest_substation_distance_m"
                ),
                "grid_feature_id": (
                    "nearest_substation_feature_id"
                ),
                "substation_id": (
                    "nearest_substation_id"
                ),
                "substation_name": (
                    "nearest_substation_name"
                ),
                "substation_type": (
                    "nearest_substation_type"
                ),
                "substation_status": (
                    "nearest_substation_status"
                ),
                "substation_city": (
                    "nearest_substation_city"
                ),
                "substation_county": (
                    "nearest_substation_county"
                ),
                "substation_line_count": (
                    "nearest_substation_line_count"
                ),
                "substation_max_voltage_kv": (
                    "nearest_substation_max_voltage_kv"
                ),
                "substation_min_voltage_kv": (
                    "nearest_substation_min_voltage_kv"
                ),
                "substation_voltage_class": (
                    "nearest_substation_voltage_class"
                ),
                "substation_max_voltage_inferred": (
                    "nearest_substation_max_voltage_inferred"
                ),
                "substation_min_voltage_inferred": (
                    "nearest_substation_min_voltage_inferred"
                ),
                "substation_source_date": (
                    "nearest_substation_source_date"
                ),
                "substation_validation_method": (
                    "nearest_substation_validation_method"
                ),
                "substation_validation_date": (
                    "nearest_substation_validation_date"
                ),
                "substation_data_confidence": (
                    "nearest_substation_data_confidence"
                ),
            }
        )
    )

    parcel_analysis = (
        parcels.merge(
            transmission_context,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
        .merge(
            substation_context,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
    )

    transmission_radius = float(
        config[
            "analysis"
        ][
            "transmission_summary_radius_m"
        ]
    )

    substation_radius = float(
        config[
            "analysis"
        ][
            "substation_summary_radius_m"
        ]
    )

    transmission_summary = (
        radius_summary(
            parcels=parcels,
            features=transmission,
            radius_m=(
                transmission_radius
            ),
            voltage_column=(
                "transmission_voltage_kv"
            ),
            owner_column=(
                "transmission_owner"
            ),
            prefix=(
                "transmission_within_5km"
            ),
        )
    )

    substation_summary = (
        radius_summary(
            parcels=parcels,
            features=substations,
            radius_m=(
                substation_radius
            ),
            voltage_column=(
                "substation_max_voltage_kv"
            ),
            owner_column=None,
            prefix=(
                "substation_within_10km"
            ),
        )
    )

    parcel_analysis = (
        parcel_analysis.merge(
            transmission_summary,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
        .merge(
            substation_summary,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
    )

    final_grid_config = (
        config[
            "inputs"
        ]["final_grid"]
    )

    final_grid_path = resolve_path(
        project_directory,
        final_grid_config["path"],
    )

    final_grid = gpd.read_file(
        final_grid_path,
        layer=final_grid_config[
            "layer"
        ],
    )

    if {
        "cell_id",
        "grid_infrastructure_score",
    }.issubset(
        final_grid.columns
    ):
        grid_scores = (
            final_grid[
                [
                    "cell_id",
                    "grid_infrastructure_score",
                ]
            ]
            .drop_duplicates(
                subset=[
                    "cell_id",
                ]
            )
            .rename(
                columns={
                    "cell_id": (
                        "statewide_cell_id"
                    ),
                    "grid_infrastructure_score": (
                        "statewide_grid_infrastructure_score"
                    ),
                }
            )
        )

        parcel_analysis = (
            parcel_analysis.merge(
                grid_scores,
                how="left",
                on="statewide_cell_id",
                validate="many_to_one",
            )
        )

    else:
        parcel_analysis[
            "statewide_grid_infrastructure_score"
        ] = np.nan

    context_config = (
        config[
            "analysis"
        ]["context_classes"]
    )

    parcel_analysis[
        "public_grid_context_class"
    ] = [
        derive_grid_context_class(
            transmission_distance_m=(
                row[
                    "nearest_transmission_distance_m"
                ]
            ),
            transmission_voltage_kv=(
                row[
                    "nearest_transmission_voltage_kv"
                ]
            ),
            substation_distance_m=(
                row[
                    "nearest_substation_distance_m"
                ]
            ),
            substation_voltage_kv=(
                row[
                    "nearest_substation_max_voltage_kv"
                ]
            ),
            maximum_nearby_voltage_kv=(
                row[
                    "transmission_within_5km_maximum_voltage_kv"
                ]
            ),
            context_config=(
                context_config
            ),
        )
        for _, row
        in parcel_analysis.iterrows()
    ]

    line_voltage_known = (
        pd.to_numeric(
            parcel_analysis[
                "nearest_transmission_voltage_kv"
            ],
            errors="coerce",
        ).notna()
    )

    station_voltage_known = (
        pd.to_numeric(
            parcel_analysis[
                "nearest_substation_max_voltage_kv"
            ],
            errors="coerce",
        ).notna()
    )

    parcel_analysis[
        "grid_data_confidence"
    ] = np.select(
        [
            (
                line_voltage_known
                & station_voltage_known
            ),
            (
                line_voltage_known
                | station_voltage_known
            ),
        ],
        [
            "HIGH",
            "MEDIUM",
        ],
        default="LOW",
    )

    parcel_analysis[
        "grid_feasibility_status"
    ] = (
        "PRELIMINARY_PUBLIC_GRID_CONTEXT_ONLY"
    )

    safeguards = config[
        "safeguards"
    ]

    parcel_analysis[
        "capacity_status"
    ] = safeguards[
        "capacity_status"
    ]

    parcel_analysis[
        "available_capacity_mw"
    ] = np.nan

    parcel_analysis[
        "utility_confirmation_required"
    ] = True

    parcel_analysis[
        "interconnection_study_required"
    ] = True

    parcel_analysis[
        "electrical_service_feasibility_confirmed"
    ] = False

    minimum_connector_length = (
        float(
            config[
                "analysis"
            ][
                "connector_minimum_length_m"
            ]
        )
    )

    transmission_connectors = (
        connector_frame(
            parcels=parcels,
            matches=(
                nearest_transmission
            ),
            features=transmission,
            evidence_kind=(
                "TRANSMISSION_CONNECTOR"
            ),
            minimum_length_m=(
                minimum_connector_length
            ),
        )
    )

    substation_connectors = (
        connector_frame(
            parcels=parcels,
            matches=(
                nearest_substation
            ),
            features=substations,
            evidence_kind=(
                "SUBSTATION_CONNECTOR"
            ),
            minimum_length_m=(
                minimum_connector_length
            ),
        )
    )

    connectors = pd.concat(
        [
            transmission_connectors,
            substation_connectors,
        ],
        ignore_index=True,
    )

    connectors = gpd.GeoDataFrame(
        connectors,
        geometry="geometry",
        crs=parcels.crs,
    )

    parcel_analysis = (
        parcel_analysis.drop(
            columns=[
                "_parcel_index",
            ],
            errors="ignore",
        )
    )

    layer_config = config[
        "layers"
    ]

    written_layers = write_layers(
        path=paths.output,
        layers=[
            (
                layer_config[
                    "parcel_analysis"
                ],
                gpd.GeoDataFrame(
                    parcel_analysis,
                    geometry="geometry",
                    crs=parcels.crs,
                ),
            ),
            (
                layer_config[
                    "transmission_lines"
                ],
                transmission,
            ),
            (
                layer_config[
                    "substations"
                ],
                substations,
            ),
            (
                layer_config[
                    "connectors"
                ],
                connectors,
            ),
        ],
    )

    context_counts = {
        str(key): int(value)
        for key, value
        in parcel_analysis[
            "public_grid_context_class"
        ].value_counts(
            dropna=False
        ).items()
    }

    line_voltage_counts = {
        str(key): int(value)
        for key, value
        in transmission[
            "transmission_voltage_class"
        ].value_counts(
            dropna=False
        ).items()
    }

    substation_voltage_counts = {
        str(key): int(value)
        for key, value
        in substations[
            "substation_voltage_class"
        ].value_counts(
            dropna=False
        ).items()
    }

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "parcel_grid_feasibility"
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
        "counts": {
            "parcel_count": (
                len(parcel_analysis)
            ),
            "scope_transmission_lines": (
                len(transmission)
            ),
            "scope_substations": (
                len(substations)
            ),
            "evidence_connectors": (
                len(connectors)
            ),
            "parcels_with_transmission_match": (
                int(
                    parcel_analysis[
                        "nearest_transmission_distance_m"
                    ].notna().sum()
                )
            ),
            "parcels_with_substation_match": (
                int(
                    parcel_analysis[
                        "nearest_substation_distance_m"
                    ].notna().sum()
                )
            ),
            "parcels_with_known_nearest_line_voltage": (
                int(
                    line_voltage_known.sum()
                )
            ),
            "parcels_with_known_nearest_substation_voltage": (
                int(
                    station_voltage_known.sum()
                )
            ),
        },
        "context_class_counts": (
            context_counts
        ),
        "transmission_voltage_class_counts": (
            line_voltage_counts
        ),
        "substation_voltage_class_counts": (
            substation_voltage_counts
        ),
        "distance_statistics_m": {
            "nearest_transmission": {
                "minimum": float(
                    parcel_analysis[
                        "nearest_transmission_distance_m"
                    ].min()
                ),
                "median": float(
                    parcel_analysis[
                        "nearest_transmission_distance_m"
                    ].median()
                ),
                "mean": float(
                    parcel_analysis[
                        "nearest_transmission_distance_m"
                    ].mean()
                ),
                "maximum": float(
                    parcel_analysis[
                        "nearest_transmission_distance_m"
                    ].max()
                ),
            },
            "nearest_substation": {
                "minimum": float(
                    parcel_analysis[
                        "nearest_substation_distance_m"
                    ].min()
                ),
                "median": float(
                    parcel_analysis[
                        "nearest_substation_distance_m"
                    ].median()
                ),
                "mean": float(
                    parcel_analysis[
                        "nearest_substation_distance_m"
                    ].mean()
                ),
                "maximum": float(
                    parcel_analysis[
                        "nearest_substation_distance_m"
                    ].max()
                ),
            },
        },
        "sources": {
            "transmission_lines": {
                "source_name": (
                    transmission_config[
                        "source_name"
                    ]
                ),
                "path": str(
                    transmission_path
                    .relative_to(
                        project_directory
                    )
                ),
                "layer": (
                    transmission_layer
                ),
                "checksum": (
                    transmission_checksum
                ),
                "fields_used": [
                    "ID",
                    "TYPE",
                    "STATUS",
                    "OWNER",
                    "VOLTAGE",
                    "VOLT_CLASS",
                    "INFERRED",
                    "SUB_1",
                    "SUB_2",
                    "SOURCE",
                    "SOURCEDATE",
                    "VAL_METHOD",
                    "VAL_DATE",
                ],
            },
            "substations": {
                "source_name": (
                    substation_config[
                        "source_name"
                    ]
                ),
                "path": str(
                    substation_path
                    .relative_to(
                        project_directory
                    )
                ),
                "layer": (
                    substation_layer
                ),
                "checksum": (
                    substation_checksum
                ),
                "fields_used": [
                    "ID",
                    "NAME",
                    "TYPE",
                    "STATUS",
                    "LINES",
                    "MAX_VOLT",
                    "MIN_VOLT",
                    "MAX_INFER",
                    "MIN_INFER",
                    "SOURCE",
                    "SOURCEDATE",
                    "VAL_METHOD",
                    "VAL_DATE",
                ],
            },
        },
        "methodology": {
            "nearest_distance": (
                "Exact planar distance from "
                "full parcel geometry to the "
                "nearest mapped infrastructure "
                "geometry in EPSG:26985."
            ),
            "nearby_summaries": {
                "transmission_radius_m": (
                    transmission_radius
                ),
                "substation_radius_m": (
                    substation_radius
                ),
            },
            "context_class": (
                "Rule-based public mapped-grid "
                "context using distance and "
                "reported voltage. It is not "
                "a capacity or interconnection "
                "determination."
            ),
        },
        "safeguards": safeguards,
        "interpretation": {
            "allowed_term": (
                "Public mapped-grid context"
            ),
            "not_allowed_terms": [
                "Available power capacity",
                "Confirmed electrical service",
                "Interconnection approved",
                "Utility-ready parcel",
            ],
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
            "[Grid feasibility] Complete | "
            f"{len(parcel_analysis):,} parcels | "
            f"{len(transmission):,} lines | "
            f"{len(substations):,} substations | "
            f"{manifest['elapsed_seconds']:.1f}s"
        ),
        flush=True,
    )

    return manifest
