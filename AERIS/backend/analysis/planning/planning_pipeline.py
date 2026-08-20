from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from shapely import make_valid, union_all

from analysis.parcels.pipeline import (
    file_sha256,
    load_config as load_parcel_config,
    parcel_scope_paths,
    read_json,
    resolve_path,
)
from analysis.planning.registry import (
    PlanningRegistry,
)
from analysis.planning.statewide_foundations import (
    acquire_foundations,
    load_yaml,
)
from analysis.statewide.grid_infrastructure_pipeline import (
    atomic_write_json,
    repair_invalid_geometries,
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def output_paths(
    *,
    config: dict[str, Any],
    project_directory: Path,
    scope_id: str,
) -> tuple[
    Path,
    Path,
]:
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

    return (
        output_root
        / f"{scope_id}.gpkg",
        manifest_root
        / f"{scope_id}.json",
    )


def first_existing_column(
    frame: pd.DataFrame,
    candidates: tuple[str, ...],
) -> str | None:
    lookup = {
        str(column).casefold(): str(
            column
        )
        for column in frame.columns
    }

    for candidate in candidates:
        value = lookup.get(
            candidate.casefold()
        )

        if value is not None:
            return value

    return None


def clean_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    result = str(value).strip()

    return result or None


def overlay_name_series(
    frame: pd.DataFrame,
) -> pd.Series:
    candidate = first_existing_column(
        frame,
        (
            "NAME",
            "ZONE_NAME",
            "ZONENAME",
            "AREA_NAME",
            "MUN_NAME",
            "PFA_NAME",
            "JURISDICTION",
            "COUNTY",
            "DISTRICT",
            "DESCRIPTION",
            "DESC",
        ),
    )

    if candidate is None:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
        frame[candidate]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def representative_point_attributes(
    *,
    parcels: gpd.GeoDataFrame,
    overlay: gpd.GeoDataFrame,
    output_columns: list[str],
) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "_parcel_index": (
                parcels.index
            )
        }
    )

    for column in output_columns:
        result[column] = None

    if overlay.empty:
        return result

    points = gpd.GeoDataFrame(
        {
            "_parcel_index": (
                parcels.index
            )
        },
        geometry=(
            parcels.geometry
            .representative_point()
        ),
        crs=parcels.crs,
    )

    joined = gpd.sjoin(
        points,
        overlay[
            [
                *output_columns,
                "geometry",
            ]
        ],
        how="left",
        predicate="intersects",
    )

    joined = (
        joined.sort_values(
            [
                "_parcel_index",
                "index_right",
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

    return joined[
        [
            "_parcel_index",
            *output_columns,
        ]
    ]


def group_intersections(
    *,
    parcels: gpd.GeoDataFrame,
    overlay: gpd.GeoDataFrame,
    name_column: str,
    prefix: str,
) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "_parcel_index": (
                parcels.index
            )
        }
    )

    result[
        f"{prefix}_feature_count"
    ] = 0

    result[
        f"{prefix}_names"
    ] = ""

    if overlay.empty:
        return result

    parcel_frame = parcels[
        [
            "geometry",
        ]
    ].copy()

    parcel_frame[
        "_parcel_index"
    ] = parcels.index

    joined = gpd.sjoin(
        parcel_frame,
        overlay[
            [
                name_column,
                "geometry",
            ]
        ],
        how="left",
        predicate="intersects",
    )

    matched = joined.loc[
        joined[
            "index_right"
        ].notna()
    ].copy()

    if matched.empty:
        return result

    count = (
        matched.groupby(
            "_parcel_index"
        )[
            "index_right"
        ]
        .nunique()
    )

    names = (
        matched.assign(
            _name=(
                matched[
                    name_column
                ]
                .astype("string")
                .fillna("")
                .str.strip()
            )
        )
        .loc[
            lambda frame: frame[
                "_name"
            ].ne("")
        ]
        .groupby(
            "_parcel_index"
        )["_name"]
        .apply(
            lambda values: "; ".join(
                sorted(
                    set(
                        str(value)
                        for value
                        in values
                    )
                )[:20]
            )
        )
    )

    result = result.set_index(
        "_parcel_index"
    )

    result.loc[
        count.index,
        f"{prefix}_feature_count",
    ] = count.astype(int)

    result.loc[
        names.index,
        f"{prefix}_names",
    ] = names

    return result.reset_index()


def overlap_acres(
    *,
    parcels: gpd.GeoDataFrame,
    overlay: gpd.GeoDataFrame,
    square_meters_per_acre: float,
) -> pd.Series:
    if overlay.empty:
        return pd.Series(
            0.0,
            index=parcels.index,
            dtype=float,
        )

    geometry = union_all(
        list(
            overlay.geometry
        )
    )

    if not geometry.is_valid:
        geometry = make_valid(
            geometry
        )

    return (
        parcels.geometry
        .intersection(
            geometry
        )
        .area
        / square_meters_per_acre
    )


def derive_planning_status(
    *,
    statewide_zoning: str | None,
    authority_status: str,
    local_zoning_status: str,
    active_development_status: str,
    permits_status: str,
) -> str:
    if not statewide_zoning:
        return (
            "STATEWIDE_ZONING_UNAVAILABLE_"
            "MANUAL_REVIEW_REQUIRED"
        )

    if authority_status in {
        "MUNICIPAL_PLANNING_REVIEW_REQUIRED",
        "INDEPENDENT_MUNICIPAL_"
        "PLANNING_REVIEW_REQUIRED",
    }:
        return (
            "MUNICIPAL_AUTHORITY_"
            "VERIFICATION_REQUIRED"
        )

    if local_zoning_status != "AVAILABLE":
        return (
            "LOCAL_ZONING_"
            "VERIFICATION_REQUIRED"
        )

    if (
        active_development_status
        != "AVAILABLE"
        or permits_status
        != "AVAILABLE"
    ):
        return (
            "LOCAL_ENTITLEMENT_"
            "VERIFICATION_REQUIRED"
        )

    return (
        "LOCAL_EVIDENCE_AVAILABLE_"
        "MANUAL_USE_REVIEW_REQUIRED"
    )


def planning_confidence(
    *,
    county_known: bool,
    statewide_zoning_known: bool,
    municipality_known: bool,
    authoritative_local_zoning: bool,
) -> str:
    if (
        county_known
        and statewide_zoning_known
        and authoritative_local_zoning
    ):
        return "HIGH"

    if (
        county_known
        and statewide_zoning_known
    ):
        return "MEDIUM"

    if county_known:
        return "LOW"

    return "INSUFFICIENT"


def build_planning_context(
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

    foundation_manifest = (
        acquire_foundations(
            config_path=config_path,
            refresh=False,
        )
    )

    foundation_path = (
        project_directory
        / foundation_manifest[
            "outputs"
        ]["geopackage"]
    )

    registry_path = resolve_path(
        project_directory,
        config[
            "registry"
        ]["path"],
    )

    registry = PlanningRegistry(
        registry_path
    )

    parcel_config_path = resolve_path(
        project_directory,
        config[
            "inputs"
        ][
            "parcel_config"
        ]["path"],
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
    ):
        raise RuntimeError(
            f"Parcel scope is missing: "
            f"{scope_id}"
        )

    output_path, manifest_path = (
        output_paths(
            config=config,
            project_directory=(
                project_directory
            ),
            scope_id=scope_id,
        )
    )

    config_checksum = file_sha256(
        config_path
    )

    registry_checksum = file_sha256(
        registry_path
    )

    parcel_checksum = file_sha256(
        parcel_paths.normalized_output
    )

    foundation_checksum = file_sha256(
        foundation_path
    )

    if (
        not refresh
        and output_path.exists()
        and manifest_path.exists()
    ):
        existing = read_json(
            manifest_path
        )

        if (
            existing.get(
                "config_checksum"
            )
            == config_checksum
            and existing.get(
                "registry_checksum"
            )
            == registry_checksum
            and existing.get(
                "parcel_scope_checksum"
            )
            == parcel_checksum
            and existing.get(
                "foundation_checksum"
            )
            == foundation_checksum
        ):
            print(
                (
                    "[Planning] Using current "
                    f"scope {scope_id}"
                ),
                flush=True,
            )

            return existing

    target_crs = str(
        config[
            "analysis"
        ]["target_crs"]
    )

    square_meters_per_acre = float(
        config[
            "analysis"
        ][
            "square_meters_per_acre"
        ]
    )

    parcels = gpd.read_file(
        parcel_paths.normalized_output,
        layer="parcels",
    ).to_crs(
        target_crs
    )

    parcels = repair_invalid_geometries(
        parcels,
        name="planning_parcels",
    ).reset_index(drop=True)

    parcels[
        "_parcel_index"
    ] = parcels.index

    scope_bounds = tuple(
        float(value)
        for value in parcels.total_bounds
    )

    layer_names = {
        "counties": (
            "county_boundaries"
        ),
        "municipalities": (
            "municipal_boundaries"
        ),
        "pfa": (
            "priority_funding_areas"
        ),
        "critical_towns": (
            "critical_area_towns"
        ),
        "critical_counties": (
            "critical_area_counties"
        ),
        "enterprise": (
            "enterprise_zones"
        ),
        "sustainable": (
            "sustainable_communities"
        ),
        "foreign_trade": (
            "foreign_trade_zones"
        ),
        "rise": "rise_zones",
        "opportunity": (
            "opportunity_zones"
        ),
    }

    overlays: dict[
        str,
        gpd.GeoDataFrame,
    ] = {}

    for key, layer_name in (
        layer_names.items()
    ):
        frame = gpd.read_file(
            foundation_path,
            layer=layer_name,
            bbox=scope_bounds,
        ).to_crs(
            target_crs
        )

        frame = (
            repair_invalid_geometries(
                frame,
                name=layer_name,
            )
            if not frame.empty
            else frame
        )

        frame[
            "_context_name"
        ] = overlay_name_series(
            frame
        )

        overlays[key] = frame

    municipality_name_column = (
        first_existing_column(
            overlays[
                "municipalities"
            ],
            (
                "MUN_NAME",
                "MUNICIPALITY",
                "NAME",
            ),
        )
    )

    municipality_overlay = (
        overlays[
            "municipalities"
        ].copy()
    )

    if municipality_name_column:
        municipality_overlay[
            "municipality_name"
        ] = (
            municipality_overlay[
                municipality_name_column
            ]
            .astype("string")
            .fillna("")
            .str.strip()
        )
    else:
        municipality_overlay[
            "municipality_name"
        ] = ""

    municipality_attributes = (
        representative_point_attributes(
            parcels=parcels,
            overlay=(
                municipality_overlay
            ),
            output_columns=[
                "municipality_name",
            ],
        )
    )

    pfa = overlays["pfa"].copy()

    pfa[
        "pfa_status"
    ] = "INSIDE_PFA"

    pfa_attributes = (
        representative_point_attributes(
            parcels=parcels,
            overlay=pfa,
            output_columns=[
                "pfa_status",
            ],
        )
    )

    result = (
        parcels.merge(
            municipality_attributes,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
        .merge(
            pfa_attributes,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )
    )

    result[
        "municipality_name"
    ] = (
        result[
            "municipality_name"
        ]
        .astype("string")
        .fillna("")
        .str.strip()
        .replace(
            "",
            pd.NA,
        )
    )

    result[
        "pfa_status"
    ] = (
        result[
            "pfa_status"
        ]
        .astype("string")
        .fillna(
            "OUTSIDE_PFA"
        )
    )

    critical = pd.concat(
        [
            overlays[
                "critical_towns"
            ],
            overlays[
                "critical_counties"
            ],
        ],
        ignore_index=True,
    )

    critical = gpd.GeoDataFrame(
        critical,
        geometry="geometry",
        crs=target_crs,
    )

    result[
        "critical_area_overlap_acres"
    ] = overlap_acres(
        parcels=result,
        overlay=critical,
        square_meters_per_acre=(
            square_meters_per_acre
        ),
    ).round(6)

    result[
        "critical_area_overlap"
    ] = result[
        "critical_area_overlap_acres"
    ].gt(0)

    incentive_specs = {
        "enterprise_zone": (
            overlays["enterprise"]
        ),
        "sustainable_community": (
            overlays[
                "sustainable"
            ]
        ),
        "foreign_trade_zone": (
            overlays[
                "foreign_trade"
            ]
        ),
        "rise_zone": (
            overlays["rise"]
        ),
        "opportunity_zone": (
            overlays[
                "opportunity"
            ]
        ),
    }

    for prefix, frame in (
        incentive_specs.items()
    ):
        joined = group_intersections(
            parcels=result,
            overlay=frame,
            name_column=(
                "_context_name"
            ),
            prefix=prefix,
        )

        result = result.merge(
            joined,
            how="left",
            on="_parcel_index",
            validate="one_to_one",
        )

    authority_values = []

    local_zoning_statuses = []
    local_zoning_notes = []
    plan_statuses = []
    active_statuses = []
    permit_statuses = []
    planning_statuses = []
    confidence_values = []

    for _, row in result.iterrows():
        county_fips = clean_text(
            row.get(
                "county_fips"
            )
        )

        municipality = clean_text(
            row.get(
                "municipality_name"
            )
        )

        if not county_fips:
            authority_values.append(
                {
                    "planning_authority_level": (
                        "UNKNOWN"
                    ),
                    "planning_authority_name": (
                        None
                    ),
                    "planning_authority_status": (
                        "JURISDICTION_UNRESOLVED"
                    ),
                    "authority_profile": (
                        None
                    ),
                }
            )

            local_zoning_statuses.append(
                "DATA_UNAVAILABLE"
            )

            local_zoning_notes.append(
                "County jurisdiction could "
                "not be resolved."
            )

            plan_statuses.append(
                "DATA_UNAVAILABLE"
            )

            active_statuses.append(
                "DATA_UNAVAILABLE"
            )

            permit_statuses.append(
                "DATA_UNAVAILABLE"
            )

            planning_statuses.append(
                "JURISDICTION_UNRESOLVED"
            )

            confidence_values.append(
                "INSUFFICIENT"
            )

            continue

        record = registry.get(
            county_fips
        )

        authority = (
            registry.resolve_authority(
                county_fips=county_fips,
                municipality_name=(
                    municipality
                ),
            )
        )

        authority_values.append(
            {
                "planning_authority_level": (
                    authority.authority_level
                ),
                "planning_authority_name": (
                    authority.authority_name
                ),
                "planning_authority_status": (
                    authority.authority_status
                ),
                "authority_profile": (
                    record.authority_profile
                ),
            }
        )

        local_zoning_statuses.append(
            record.zoning.status
        )

        local_zoning_notes.append(
            record.zoning.note
        )

        plan_statuses.append(
            record.comprehensive_plan.status
        )

        active_statuses.append(
            record.active_development.status
        )

        permit_statuses.append(
            record.permits.status
        )

        statewide_zoning = (
            clean_text(
                row.get(
                    "zoning_code"
                )
            )
        )

        authority_status = (
            authority.authority_status
        )

        planning_statuses.append(
            derive_planning_status(
                statewide_zoning=(
                    statewide_zoning
                ),
                authority_status=(
                    authority_status
                ),
                local_zoning_status=(
                    record.zoning.status
                ),
                active_development_status=(
                    record.active_development.status
                ),
                permits_status=(
                    record.permits.status
                ),
            )
        )

        confidence_values.append(
            planning_confidence(
                county_known=True,
                statewide_zoning_known=(
                    statewide_zoning
                    is not None
                ),
                municipality_known=(
                    municipality
                    is not None
                ),
                authoritative_local_zoning=(
                    record.zoning
                    .authoritative_local_geometry
                ),
            )
        )

    authority_frame = pd.DataFrame(
        authority_values
    )

    for column in (
        "planning_authority_level",
        "planning_authority_name",
        "planning_authority_status",
        "authority_profile",
    ):
        result[column] = (
            authority_frame[column]
            .to_numpy()
        )

    result[
        "statewide_zoning_status"
    ] = np.where(
        result[
            "zoning_code"
        ]
        .astype("string")
        .fillna("")
        .str.strip()
        .ne(""),
        (
            "STATEWIDE_PARCEL_"
            "ZONING_REPORTED"
        ),
        (
            "STATEWIDE_PARCEL_"
            "ZONING_UNAVAILABLE"
        ),
    )

    result[
        "local_zoning_source_status"
    ] = local_zoning_statuses

    result[
        "local_zoning_source_note"
    ] = local_zoning_notes

    result[
        "comprehensive_plan_source_status"
    ] = plan_statuses

    result[
        "active_development_source_status"
    ] = active_statuses

    result[
        "permit_source_status"
    ] = permit_statuses

    result[
        "planning_review_status"
    ] = planning_statuses

    result[
        "planning_data_confidence"
    ] = confidence_values

    result[
        "local_zoning_verified"
    ] = False

    result[
        "permitted_use_determined"
    ] = False

    result[
        "active_development_clear"
    ] = False

    result[
        "permit_clearance_determined"
    ] = False

    result[
        "entitlement_clearance_determined"
    ] = False

    result[
        "manual_local_verification_required"
    ] = True

    context_layers = []

    context_map = {
        "municipal_boundary": (
            overlays[
                "municipalities"
            ]
        ),
        "priority_funding_area": (
            overlays["pfa"]
        ),
        "critical_area": (
            critical
        ),
        "enterprise_zone": (
            overlays[
                "enterprise"
            ]
        ),
        "sustainable_community": (
            overlays[
                "sustainable"
            ]
        ),
        "foreign_trade_zone": (
            overlays[
                "foreign_trade"
            ]
        ),
        "rise_zone": (
            overlays["rise"]
        ),
        "opportunity_zone": (
            overlays[
                "opportunity"
            ]
        ),
    }

    for context_kind, frame in (
        context_map.items()
    ):
        if frame.empty:
            continue

        layer = frame.copy()

        layer[
            "planning_context_kind"
        ] = context_kind

        if "_context_name" not in layer:
            layer[
                "_context_name"
            ] = overlay_name_series(
                layer
            )

        layer[
            "planning_context_name"
        ] = layer[
            "_context_name"
        ]

        context_layers.append(
            layer[
                [
                    "planning_context_kind",
                    "planning_context_name",
                    "geometry",
                ]
            ]
        )

    context_overlays = (
        gpd.GeoDataFrame(
            pd.concat(
                context_layers,
                ignore_index=True,
            ),
            geometry="geometry",
            crs=target_crs,
        )
        if context_layers
        else gpd.GeoDataFrame(
            columns=[
                "planning_context_kind",
                "planning_context_name",
                "geometry",
            ],
            geometry="geometry",
            crs=target_crs,
        )
    )

    result = result.drop(
        columns=[
            "_parcel_index",
        ],
        errors="ignore",
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path.exists():
        output_path.unlink()

    result.to_file(
        output_path,
        layer=config[
            "layers"
        ]["parcel_analysis"],
        driver="GPKG",
        index=False,
    )

    if not context_overlays.empty:
        context_overlays.to_file(
            output_path,
            layer=config[
                "layers"
            ]["context_overlays"],
            driver="GPKG",
            mode="a",
            index=False,
        )

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "parcel_planning_context"
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
                len(result)
            ),
            "municipal_parcels": int(
                result[
                    "municipality_name"
                ].notna().sum()
            ),
            "pfa_parcels": int(
                result[
                    "pfa_status"
                ].eq(
                    "INSIDE_PFA"
                ).sum()
            ),
            "critical_area_parcels": int(
                result[
                    "critical_area_overlap"
                ].sum()
            ),
            "context_overlay_features": (
                len(
                    context_overlays
                )
            ),
        },
        "planning_review_status_counts": {
            str(key): int(value)
            for key, value
            in result[
                "planning_review_status"
            ].value_counts(
                dropna=False
            ).items()
        },
        "authority_status_counts": {
            str(key): int(value)
            for key, value
            in result[
                "planning_authority_status"
            ].value_counts(
                dropna=False
            ).items()
        },
        "planning_data_confidence_counts": {
            str(key): int(value)
            for key, value
            in result[
                "planning_data_confidence"
            ].value_counts(
                dropna=False
            ).items()
        },
        "registry_coverage": (
            registry.coverage_summary()
        ),
        "safeguards": (
            config[
                "safeguards"
            ]
        ),
        "interpretation": {
            "statewide_zoning": (
                "Statewide parcel attribute; "
                "local authoritative zoning "
                "verification remains required."
            ),
            "active_development": (
                "Unavailable automation is "
                "not interpreted as no active "
                "development."
            ),
            "permitted_use": (
                "AERIS does not determine "
                "whether a data center is "
                "permitted by right."
            ),
        },
        "config_checksum": (
            file_sha256(
                config_path
            )
        ),
        "registry_checksum": (
            file_sha256(
                registry_path
            )
        ),
        "parcel_scope_checksum": (
            file_sha256(
                parcel_paths.normalized_output
            )
        ),
        "foundation_checksum": (
            file_sha256(
                foundation_path
            )
        ),
        "outputs": {
            "geopackage": str(
                output_path.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "geopackage": (
                file_sha256(
                    output_path
                )
            ),
        },
        "elapsed_seconds": round(
            time.monotonic()
            - started,
            3,
        ),
    }

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    atomic_write_json(
        manifest_path,
        manifest,
    )

    print(
        (
            "[Planning] Complete | "
            f"{len(result):,} parcels | "
            f"{manifest['elapsed_seconds']:.1f}s"
        ),
        flush=True,
    )

    return manifest
