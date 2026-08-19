from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import yaml
from requests.adapters import HTTPAdapter
from shapely import (
    GeometryCollection,
    LineString,
    Point,
    make_valid,
    union_all,
)
from shapely.geometry.base import BaseGeometry
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class AviationPaths:
    archive: Path
    geopackage: Path
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


def resolve_path(
    project_directory: Path,
    relative_path: str,
) -> Path:
    return (
        project_directory
        / relative_path
    ).resolve()


def file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def atomic_write_json(
    path: Path,
    payload: dict[str, Any],
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
            payload,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def aviation_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
) -> AviationPaths:
    outputs = config["outputs"]

    return AviationPaths(
        archive=resolve_path(
            project_directory,
            outputs["archive"]["path"],
        ),
        geopackage=resolve_path(
            project_directory,
            outputs[
                "geopackage"
            ]["path"],
        ),
        manifest=resolve_path(
            project_directory,
            outputs[
                "manifest"
            ]["path"],
        ),
    )


def http_session() -> requests.Session:
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=1.25,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=(
            "GET",
        ),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": (
                "AERIS/0.4 "
                "FAA-NASR-aviation-screen"
            ),
            "Accept": (
                "application/zip,"
                "application/octet-stream,"
                "*/*"
            ),
        }
    )

    return session


def download_archive(
    *,
    url: str,
    path: Path,
    timeout_seconds: int,
    refresh: bool,
) -> bool:
    if path.exists() and not refresh:
        print(
            (
                "[Aviation] Using cached "
                f"FAA archive: {path}"
            ),
            flush=True,
        )

        return True

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".part"
    )

    if temporary.exists():
        temporary.unlink()

    print(
        (
            "[Aviation] Downloading FAA "
            "NASR APT CSV archive"
        ),
        flush=True,
    )

    with http_session().get(
        url,
        stream=True,
        timeout=timeout_seconds,
    ) as response:
        response.raise_for_status()

        with temporary.open("wb") as output:
            for block in (
                response.iter_content(
                    chunk_size=1024 * 1024
                )
            ):
                if block:
                    output.write(block)

    if not zipfile.is_zipfile(
        temporary
    ):
        temporary.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "FAA NASR response was not "
            "a valid ZIP archive."
        )

    temporary.replace(path)

    return False


def normalize_headers(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    result.columns = [
        str(column)
        .replace("\ufeff", "")
        .strip()
        .upper()
        for column in result.columns
    ]

    return result


def find_archive_member(
    archive: zipfile.ZipFile,
    expected_basename: str,
) -> str:
    expected = (
        expected_basename
        .strip()
        .casefold()
    )

    matches = [
        name
        for name in archive.namelist()
        if (
            Path(name).name
            .casefold()
            == expected
        )
    ]

    if len(matches) != 1:
        raise RuntimeError(
            (
                "Expected exactly one "
                f"{expected_basename!r} in "
                "FAA archive; found "
                f"{len(matches)}."
            )
        )

    return matches[0]


def read_csv_member(
    archive: zipfile.ZipFile,
    member: str,
) -> pd.DataFrame:
    with archive.open(member) as handle:
        frame = pd.read_csv(
            handle,
            dtype="string",
            keep_default_na=False,
            low_memory=False,
            encoding="utf-8-sig",
        )

    return normalize_headers(
        frame
    )


def text_column(
    frame: pd.DataFrame,
    name: str,
) -> pd.Series:
    if name not in frame:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
        frame[name]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def numeric_column(
    frame: pd.DataFrame,
    name: str,
) -> pd.Series:
    if name not in frame:
        return pd.Series(
            np.nan,
            index=frame.index,
            dtype=float,
        )

    return pd.to_numeric(
        frame[name],
        errors="coerce",
    )


def scalar_text(
    row: pd.Series | None,
    name: str,
) -> str:
    if row is None or name not in row:
        return ""

    value = row[name]

    try:
        if pd.isna(value):
            return ""
    except (
        TypeError,
        ValueError,
    ):
        pass

    return str(value).strip()


def scalar_number(
    row: pd.Series | None,
    name: str,
) -> float | None:
    if row is None or name not in row:
        return None

    try:
        value = float(row[name])
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not np.isfinite(value):
        return None

    return value


def empty_frame(
    *,
    crs: str,
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "geometry": [],
        },
        geometry="geometry",
        crs=crs,
    )


def study_area_geometry(
    *,
    config: dict[str, Any],
    project_directory: Path,
) -> BaseGeometry:
    input_config = config[
        "inputs"
    ]["study_area_grid"]

    path = resolve_path(
        project_directory,
        input_config["path"],
    )

    if not path.exists():
        raise RuntimeError(
            "Statewide study-area grid "
            f"is missing: {path}"
        )

    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    grid = gpd.read_file(
        path,
        layer=input_config[
            "layer"
        ],
    ).to_crs(
        target_crs
    )

    geometry = union_all(
        list(grid.geometry)
    )

    if not geometry.is_valid:
        geometry = make_valid(
            geometry
        )

    return geometry.buffer(
        float(
            config[
                "analysis"
            ][
                "study_area_buffer_m"
            ]
        )
    )


def build_airport_points(
    *,
    airports: pd.DataFrame,
    target_crs: str,
) -> gpd.GeoDataFrame:
    frame = airports.copy()

    frame["SITE_NO"] = text_column(
        frame,
        "SITE_NO",
    )

    frame["ARPT_ID"] = text_column(
        frame,
        "ARPT_ID",
    )

    latitude = numeric_column(
        frame,
        "LAT_DECIMAL",
    )

    longitude = numeric_column(
        frame,
        "LONG_DECIMAL",
    )

    valid = (
        latitude.between(
            -90,
            90,
            inclusive="both",
        )
        & longitude.between(
            -180,
            180,
            inclusive="both",
        )
    )

    frame = frame.loc[
        valid
    ].copy()

    latitude = latitude.loc[
        valid
    ]

    longitude = longitude.loc[
        valid
    ]

    fields = [
        field
        for field in (
            "SITE_NO",
            "SITE_TYPE_CODE",
            "ARPT_ID",
            "ICAO_ID",
            "ARPT_NAME",
            "STATE_CODE",
            "STATE_NAME",
            "COUNTY_NAME",
            "CITY",
            "OWNERSHIP_TYPE_CODE",
            "FACILITY_USE_CODE",
            "ARPT_STATUS",
            "ACREAGE",
            "ELEV",
            "EFF_DATE",
            "ASP_ANLYS_DTRM_CODE",
        )
        if field in frame.columns
    ]

    result = gpd.GeoDataFrame(
        frame[fields].copy(),
        geometry=gpd.points_from_xy(
            longitude,
            latitude,
        ),
        crs="EPSG:4326",
    ).to_crs(
        target_crs
    )

    result[
        "airport_key"
    ] = (
        result["SITE_NO"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    result[
        "facility_kind"
    ] = "LANDING_FACILITY"

    result[
        "source_product"
    ] = "FAA_NASR_APT_BASE"

    return result


def farthest_pair(
    points: list[Point],
) -> tuple[
    Point,
    Point,
] | None:
    unique: list[Point] = []

    seen: set[
        tuple[float, float]
    ] = set()

    for point in points:
        key = (
            round(
                float(point.x),
                4,
            ),
            round(
                float(point.y),
                4,
            ),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(point)

    if len(unique) < 2:
        return None

    return max(
        itertools.combinations(
            unique,
            2,
        ),
        key=lambda pair: (
            pair[0].distance(
                pair[1]
            )
        ),
    )


def runway_notice_distance_ft(
    *,
    longest_runway_ft: float,
    long_runway_threshold_ft: float,
    long_runway_distance_ft: float,
    short_runway_distance_ft: float,
) -> float:
    if (
        longest_runway_ft
        > long_runway_threshold_ft
    ):
        return long_runway_distance_ft

    return short_runway_distance_ft


def physical_runway_polygon(
    *,
    centerline: LineString,
    width_ft: float,
    feet_to_meters: float,
    extra_buffer_m: float,
) -> BaseGeometry:
    half_width_m = (
        width_ft
        * feet_to_meters
        / 2.0
        + extra_buffer_m
    )

    if half_width_m <= 0:
        return GeometryCollection()

    geometry = centerline.buffer(
        half_width_m,
        cap_style=2,
        join_style=2,
    )

    if not geometry.is_valid:
        geometry = make_valid(
            geometry
        )

    return geometry


def build_runway_layers(
    *,
    airport_points: gpd.GeoDataFrame,
    runways: pd.DataFrame,
    runway_ends: pd.DataFrame,
    config: dict[str, Any],
    regional_geometry: BaseGeometry,
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    dict[str, Any],
]:
    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    analysis = config[
        "analysis"
    ]

    notice_config = analysis[
        "notice_screening"
    ]

    feet_to_meters = float(
        analysis[
            "feet_to_meters"
        ]
    )

    square_meters_per_acre = float(
        analysis[
            "square_meters_per_acre"
        ]
    )

    runways = runways.copy()
    runway_ends = (
        runway_ends.copy()
    )

    for frame in (
        runways,
        runway_ends,
    ):
        frame["SITE_NO"] = (
            text_column(
                frame,
                "SITE_NO",
            )
        )

        frame["ARPT_ID"] = (
            text_column(
                frame,
                "ARPT_ID",
            )
        )

        frame["RWY_ID"] = (
            text_column(
                frame,
                "RWY_ID",
            )
        )

        frame[
            "_RUNWAY_KEY"
        ] = (
            frame["SITE_NO"]
            + "|"
            + frame["RWY_ID"]
        )

    local_site_numbers = set(
        airport_points[
            "SITE_NO"
        ].astype(str)
    )

    runways = runways.loc[
        runways[
            "SITE_NO"
        ].isin(
            local_site_numbers
        )
    ].copy()

    runway_ends = (
        runway_ends.loc[
            runway_ends[
                "SITE_NO"
            ].isin(
                local_site_numbers
            )
        ].copy()
    )

    runways[
        "_RWY_LEN_NUM"
    ] = numeric_column(
        runways,
        "RWY_LEN",
    )

    runways[
        "_RWY_WIDTH_NUM"
    ] = numeric_column(
        runways,
        "RWY_WIDTH",
    )

    longest_by_site = (
        runways.groupby(
            "SITE_NO"
        )[
            "_RWY_LEN_NUM"
        ]
        .max()
        .to_dict()
    )

    latitude = numeric_column(
        runway_ends,
        "LAT_DECIMAL",
    )

    longitude = numeric_column(
        runway_ends,
        "LONG_DECIMAL",
    )

    valid_end = (
        latitude.between(
            -90,
            90,
            inclusive="both",
        )
        & longitude.between(
            -180,
            180,
            inclusive="both",
        )
    )

    runway_ends = (
        runway_ends.loc[
            valid_end
        ].copy()
    )

    end_points = (
        gpd.GeoDataFrame(
            runway_ends,
            geometry=(
                gpd.points_from_xy(
                    longitude.loc[
                        valid_end
                    ],
                    latitude.loc[
                        valid_end
                    ],
                )
            ),
            crs="EPSG:4326",
        )
        .to_crs(
            target_crs
        )
    )

    runway_lookup = (
        runways.sort_values(
            [
                "SITE_NO",
                "RWY_ID",
            ]
        )
        .drop_duplicates(
            subset=[
                "_RUNWAY_KEY",
            ],
            keep="first",
        )
        .set_index(
            "_RUNWAY_KEY",
            drop=False,
        )
    )

    airport_lookup = (
        airport_points
        .sort_values(
            "SITE_NO"
        )
        .drop_duplicates(
            subset=[
                "SITE_NO",
            ],
            keep="first",
        )
        .set_index(
            "SITE_NO",
            drop=False,
        )
    )

    ils_by_site = (
        runway_ends.assign(
            _ILS_PRESENT=(
                text_column(
                    runway_ends,
                    "ILS_TYPE",
                )
                .str.upper()
                .notna()
                & text_column(
                    runway_ends,
                    "ILS_TYPE",
                )
                .str.strip()
                .ne("")
            )
        )
        .groupby(
            "SITE_NO"
        )[
            "_ILS_PRESENT"
        ]
        .any()
        .to_dict()
    )

    public_use_codes = {
        str(value)
        .strip()
        .upper()
        for value
        in analysis.get(
            "public_use_codes",
            config.get(
                "public_use_codes",
                [],
            ),
        )
    }

    centerline_records: list[
        dict[str, Any]
    ] = []

    hard_records: list[
        dict[str, Any]
    ] = []

    review_records: list[
        dict[str, Any]
    ] = []

    incomplete_endpoint_count = 0
    missing_width_count = 0

    for runway_key, group in (
        end_points.groupby(
            "_RUNWAY_KEY",
            sort=True,
        )
    ):
        pair = farthest_pair(
            list(
                group.geometry
            )
        )

        if pair is None:
            incomplete_endpoint_count += 1
            continue

        first_point, second_point = (
            pair
        )

        centerline = LineString(
            [
                first_point,
                second_point,
            ]
        )

        runway_row = (
            runway_lookup.loc[
                runway_key
            ]
            if runway_key
            in runway_lookup.index
            else None
        )

        site_no = str(
            group.iloc[0][
                "SITE_NO"
            ]
        )

        runway_id = str(
            group.iloc[0][
                "RWY_ID"
            ]
        )

        airport_row = (
            airport_lookup.loc[
                site_no
            ]
            if site_no
            in airport_lookup.index
            else None
        )

        reported_length_ft = (
            scalar_number(
                runway_row,
                "_RWY_LEN_NUM",
            )
        )

        reported_width_ft = (
            scalar_number(
                runway_row,
                "_RWY_WIDTH_NUM",
            )
        )

        actual_length_m = float(
            centerline.length
        )

        actual_length_ft = (
            actual_length_m
            / feet_to_meters
        )

        effective_length_ft = (
            reported_length_ft
            if (
                reported_length_ft
                is not None
                and reported_length_ft > 0
            )
            else actual_length_ft
        )

        longest_runway_ft = float(
            longest_by_site.get(
                site_no,
                effective_length_ft,
            )
            or effective_length_ft
        )

        notice_distance_ft = (
            runway_notice_distance_ft(
                longest_runway_ft=(
                    longest_runway_ft
                ),
                long_runway_threshold_ft=float(
                    notice_config[
                        "long_runway_threshold_ft"
                    ]
                ),
                long_runway_distance_ft=float(
                    notice_config[
                        "long_runway_distance_ft"
                    ]
                ),
                short_runway_distance_ft=float(
                    notice_config[
                        "short_runway_distance_ft"
                    ]
                ),
            )
        )

        notice_distance_m = (
            notice_distance_ft
            * feet_to_meters
        )

        facility_use_code = (
            scalar_text(
                airport_row,
                "FACILITY_USE_CODE",
            ).upper()
        )

        likely_public_use = (
            facility_use_code
            in public_use_codes
            or "PUBLIC"
            in facility_use_code
        )

        instrument_approach = bool(
            ils_by_site.get(
                site_no,
                False,
            )
        )

        if (
            likely_public_use
            or instrument_approach
        ):
            applicability = (
                "LIKELY_APPLICABLE"
            )

        else:
            applicability = (
                "NOT_FULLY_EVALUATED"
            )

        airport_id = (
            scalar_text(
                airport_row,
                "ARPT_ID",
            )
            or str(
                group.iloc[0][
                    "ARPT_ID"
                ]
            )
        )

        common = {
            "runway_key": (
                runway_key
            ),
            "site_no": site_no,
            "airport_id": (
                airport_id
            ),
            "icao_id": scalar_text(
                airport_row,
                "ICAO_ID",
            ),
            "airport_name": (
                scalar_text(
                    airport_row,
                    "ARPT_NAME",
                )
            ),
            "state_code": (
                scalar_text(
                    airport_row,
                    "STATE_CODE",
                )
            ),
            "county_name": (
                scalar_text(
                    airport_row,
                    "COUNTY_NAME",
                )
            ),
            "city": scalar_text(
                airport_row,
                "CITY",
            ),
            "runway_id": runway_id,
            "reported_length_ft": (
                reported_length_ft
            ),
            "reported_width_ft": (
                reported_width_ft
            ),
            "actual_endpoint_length_m": (
                round(
                    actual_length_m,
                    3,
                )
            ),
            "airport_longest_runway_ft": (
                round(
                    longest_runway_ft,
                    3,
                )
            ),
            "surface_type_code": (
                scalar_text(
                    runway_row,
                    "SURFACE_TYPE_CODE",
                )
            ),
            "runway_condition": (
                scalar_text(
                    runway_row,
                    "COND",
                )
            ),
            "facility_use_code": (
                facility_use_code
            ),
            "instrument_approach_indicator": (
                instrument_approach
            ),
            "part77_applicability": (
                applicability
            ),
            "source_cycle": (
                config[
                    "snapshot_label"
                ]
            ),
        }

        centerline_records.append(
            {
                **common,
                "geometry": centerline,
            }
        )

        if (
            reported_width_ft
            is not None
            and reported_width_ft
            >= float(
                analysis[
                    "minimum_runway_width_ft"
                ]
            )
        ):
            hard_geometry = (
                physical_runway_polygon(
                    centerline=(
                        centerline
                    ),
                    width_ft=(
                        reported_width_ft
                    ),
                    feet_to_meters=(
                        feet_to_meters
                    ),
                    extra_buffer_m=float(
                        analysis[
                            "runway_hard_conflict_extra_buffer_m"
                        ]
                    ),
                )
            )

            hard_records.append(
                {
                    **common,
                    "constraint_id": (
                        "aviation"
                    ),
                    "constraint_label": (
                        "FAA physical "
                        "runway pavement"
                    ),
                    "hard_conflict_basis": (
                        "PHYSICAL_RUNWAY_"
                        "PAVEMENT"
                    ),
                    "subtract_from_envelope": (
                        True
                    ),
                    "hard_conflict_area_acres": (
                        round(
                            hard_geometry.area
                            / square_meters_per_acre,
                            6,
                        )
                    ),
                    "geometry": (
                        hard_geometry
                    ),
                }
            )

        else:
            missing_width_count += 1

        review_geometry = (
            centerline.buffer(
                notice_distance_m
            )
        )

        review_records.append(
            {
                **common,
                "constraint_id": (
                    "aviation_review"
                ),
                "constraint_label": (
                    "FAA Part 77 "
                    "notice-distance screen"
                ),
                "notice_distance_ft": (
                    notice_distance_ft
                ),
                "notice_distance_m": (
                    round(
                        notice_distance_m,
                        3,
                    )
                ),
                "notice_basis": (
                    (
                        "LONGEST_RUNWAY_"
                        "OVER_3200_FT"
                    )
                    if (
                        longest_runway_ft
                        > float(
                            notice_config[
                                "long_runway_threshold_ft"
                            ]
                        )
                    )
                    else (
                        "LONGEST_RUNWAY_"
                        "3200_FT_OR_LESS"
                    )
                ),
                "proposed_height_evaluated": (
                    False
                ),
                "faa_determination_made": (
                    False
                ),
                "subtract_from_envelope": (
                    False
                ),
                "geometry": (
                    review_geometry
                ),
            }
        )

    heliport_codes = {
        str(value)
        .strip()
        .upper()
        for value
        in notice_config.get(
            "heliport_site_type_codes",
            [],
        )
    }

    runway_sites = set(
        runways[
            "SITE_NO"
        ].astype(str)
    )

    heliports = (
        airport_points.loc[
            airport_points[
                "SITE_TYPE_CODE"
            ]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
            .isin(
                heliport_codes
            )
            & ~airport_points[
                "SITE_NO"
            ].astype(str)
            .isin(
                runway_sites
            )
        ]
        .copy()
    )

    heliport_distance_ft = float(
        notice_config[
            "heliport_distance_ft"
        ]
    )

    heliport_distance_m = (
        heliport_distance_ft
        * feet_to_meters
    )

    for _, row in (
        heliports.iterrows()
    ):
        review_records.append(
            {
                "runway_key": (
                    str(
                        row["SITE_NO"]
                    )
                    + "|HELIPORT"
                ),
                "site_no": str(
                    row["SITE_NO"]
                ),
                "airport_id": str(
                    row.get(
                        "ARPT_ID",
                        "",
                    )
                ),
                "icao_id": str(
                    row.get(
                        "ICAO_ID",
                        "",
                    )
                ),
                "airport_name": str(
                    row.get(
                        "ARPT_NAME",
                        "",
                    )
                ),
                "state_code": str(
                    row.get(
                        "STATE_CODE",
                        "",
                    )
                ),
                "county_name": str(
                    row.get(
                        "COUNTY_NAME",
                        "",
                    )
                ),
                "city": str(
                    row.get(
                        "CITY",
                        "",
                    )
                ),
                "runway_id": (
                    "HELIPORT"
                ),
                "reported_length_ft": (
                    None
                ),
                "reported_width_ft": (
                    None
                ),
                "actual_endpoint_length_m": (
                    None
                ),
                "airport_longest_runway_ft": (
                    None
                ),
                "surface_type_code": (
                    ""
                ),
                "runway_condition": (
                    ""
                ),
                "facility_use_code": (
                    str(
                        row.get(
                            "FACILITY_USE_CODE",
                            "",
                        )
                    )
                ),
                "instrument_approach_indicator": (
                    False
                ),
                "part77_applicability": (
                    "NOT_FULLY_EVALUATED"
                ),
                "source_cycle": (
                    config[
                        "snapshot_label"
                    ]
                ),
                "constraint_id": (
                    "aviation_review"
                ),
                "constraint_label": (
                    "FAA Part 77 "
                    "heliport notice-distance "
                    "screen"
                ),
                "notice_distance_ft": (
                    heliport_distance_ft
                ),
                "notice_distance_m": (
                    round(
                        heliport_distance_m,
                        3,
                    )
                ),
                "notice_basis": (
                    "HELIPORT_5000_FT"
                ),
                "proposed_height_evaluated": (
                    False
                ),
                "faa_determination_made": (
                    False
                ),
                "subtract_from_envelope": (
                    False
                ),
                "geometry": (
                    row.geometry.buffer(
                        heliport_distance_m
                    )
                ),
            }
        )

    def make_frame(
        records: list[
            dict[str, Any]
        ],
    ) -> gpd.GeoDataFrame:
        if not records:
            return empty_frame(
                crs=target_crs
            )

        result = gpd.GeoDataFrame(
            records,
            geometry="geometry",
            crs=target_crs,
        )

        result.geometry = (
            result.geometry.map(
                make_valid
            )
        )

        return result.loc[
            result.geometry.notna()
            & ~result.geometry.is_empty
            & result.geometry.intersects(
                regional_geometry
            )
        ].copy()

    centerlines = make_frame(
        centerline_records
    )

    hard_conflicts = make_frame(
        hard_records
    )

    review_areas = make_frame(
        review_records
    )

    diagnostics = {
        "runway_source_rows": (
            len(runways)
        ),
        "runway_end_source_rows": (
            len(runway_ends)
        ),
        "incomplete_endpoint_groups": (
            incomplete_endpoint_count
        ),
        "runways_missing_usable_width": (
            missing_width_count
        ),
        "heliport_review_features": (
            len(heliports)
        ),
    }

    return (
        centerlines,
        hard_conflicts,
        review_areas,
        diagnostics,
    )


def write_geopackage_layers(
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
            "FAA aviation pipeline "
            "produced no writable layers."
        )

    return written


def build_faa_aviation_snapshot(
    *,
    config_path: Path,
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

    paths = aviation_paths(
        config=config,
        project_directory=(
            project_directory
        ),
    )

    used_cached_archive = (
        download_archive(
            url=str(
                config[
                    "source"
                ]["apt_csv_url"]
            ),
            path=paths.archive,
            timeout_seconds=int(
                config[
                    "source"
                ][
                    "timeout_seconds"
                ]
            ),
            refresh=refresh,
        )
    )

    print(
        "[Aviation] Reading NASR CSV files",
        flush=True,
    )

    with zipfile.ZipFile(
        paths.archive
    ) as archive:
        member_config = config[
            "source"
        ]["csv_members"]

        airport_member = (
            find_archive_member(
                archive,
                member_config[
                    "airports"
                ],
            )
        )

        runway_member = (
            find_archive_member(
                archive,
                member_config[
                    "runways"
                ],
            )
        )

        runway_end_member = (
            find_archive_member(
                archive,
                member_config[
                    "runway_ends"
                ],
            )
        )

        airport_table = (
            read_csv_member(
                archive,
                airport_member,
            )
        )

        runway_table = (
            read_csv_member(
                archive,
                runway_member,
            )
        )

        runway_end_table = (
            read_csv_member(
                archive,
                runway_end_member,
            )
        )

    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    regional_geometry = (
        study_area_geometry(
            config=config,
            project_directory=(
                project_directory
            ),
        )
    )

    airports = build_airport_points(
        airports=airport_table,
        target_crs=target_crs,
    )

    airports = airports.loc[
        airports.geometry.intersects(
            regional_geometry
        )
    ].copy()

    print(
        (
            "[Aviation] Regional landing "
            f"facilities: {len(airports):,}"
        ),
        flush=True,
    )

    (
        centerlines,
        hard_conflicts,
        notice_screening,
        diagnostics,
    ) = build_runway_layers(
        airport_points=airports,
        runways=runway_table,
        runway_ends=(
            runway_end_table
        ),
        config=config,
        regional_geometry=(
            regional_geometry
        ),
    )

    layer_config = config[
        "layers"
    ]

    written_layers = (
        write_geopackage_layers(
            path=paths.geopackage,
            layers=[
                (
                    layer_config[
                        "airports"
                    ],
                    airports,
                ),
                (
                    layer_config[
                        "runway_centerlines"
                    ],
                    centerlines,
                ),
                (
                    layer_config[
                        "runway_hard_conflicts"
                    ],
                    hard_conflicts,
                ),
                (
                    layer_config[
                        "aviation_notice_screening"
                    ],
                    notice_screening,
                ),
            ],
        )
    )

    site_type_counts = {
        str(key): int(value)
        for key, value
        in airports[
            "SITE_TYPE_CODE"
        ].astype("string")
        .fillna("<NULL>")
        .value_counts(
            dropna=False
        )
        .items()
    }

    state_counts = {
        str(key): int(value)
        for key, value
        in airports[
            "STATE_CODE"
        ].astype("string")
        .fillna("<NULL>")
        .value_counts(
            dropna=False
        )
        .items()
    }

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "faa_nasr_aviation"
        ),
        "pipeline_version": (
            config[
                "pipeline_version"
            ]
        ),
        "generated_at_utc": (
            utc_now()
        ),
        "snapshot_label": (
            config[
                "snapshot_label"
            ]
        ),
        "source": {
            "provider": (
                config[
                    "source"
                ]["provider"]
            ),
            "product": (
                config[
                    "source"
                ]["product"]
            ),
            "subscription_page_url": (
                config[
                    "source"
                ][
                    "subscription_page_url"
                ]
            ),
            "apt_csv_url": (
                config[
                    "source"
                ]["apt_csv_url"]
            ),
            "archive": str(
                paths.archive.relative_to(
                    project_directory
                )
            ),
            "archive_sha256": (
                file_sha256(
                    paths.archive
                )
            ),
            "used_cached_archive": (
                used_cached_archive
            ),
            "csv_members": {
                "airports": (
                    airport_member
                ),
                "runways": (
                    runway_member
                ),
                "runway_ends": (
                    runway_end_member
                ),
            },
        },
        "counts": {
            "airport_source_rows": (
                len(airport_table)
            ),
            "regional_airport_points": (
                len(airports)
            ),
            "regional_runway_centerlines": (
                len(centerlines)
            ),
            "regional_runway_hard_conflicts": (
                len(hard_conflicts)
            ),
            "regional_notice_screening_features": (
                len(
                    notice_screening
                )
            ),
        },
        "diagnostics": diagnostics,
        "site_type_counts": (
            site_type_counts
        ),
        "state_counts": (
            state_counts
        ),
        "methodology": {
            "hard_conflict": (
                "Physical runway pavement "
                "constructed from FAA runway-"
                "end coordinates and reported "
                "runway width."
            ),
            "notice_screening": (
                "Horizontal screening extent "
                "from 14 CFR 77.9. Proposed "
                "height, shielding, and formal "
                "FAA applicability are not "
                "evaluated."
            ),
            "airport_property_boundary": (
                "Not available from this "
                "NASR implementation and not "
                "inferred from airport acreage."
            ),
        },
        "safeguards": (
            config[
                "safeguards"
            ]
        ),
        "written_layers": (
            written_layers
        ),
        "outputs": {
            "geopackage": str(
                paths.geopackage
                .relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "geopackage": (
                file_sha256(
                    paths.geopackage
                )
            ),
        },
        "elapsed_seconds": round(
            time.monotonic()
            - started,
            3,
        ),
    }

    atomic_write_json(
        paths.manifest,
        manifest,
    )

    print(
        (
            "[Aviation] Complete | "
            f"{len(centerlines):,} runways | "
            f"{len(hard_conflicts):,} "
            "physical conflicts | "
            f"{len(notice_screening):,} "
            "notice screens"
        ),
        flush=True,
    )

    return manifest
