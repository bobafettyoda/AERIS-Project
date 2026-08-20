from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[1]
)

PROJECT_DIRECTORY = (
    BACKEND_DIRECTORY.parent
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review parcel-level public "
            "electrical-grid context."
        )
    )

    parser.add_argument(
        "scope_id",
    )

    return parser.parse_args()


def main() -> None:
    options = arguments()

    manifest_path = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / "parcel_grid_feasibility"
        / f"{options.scope_id}.json"
    )

    require(
        manifest_path.exists(),
        (
            "Grid-feasibility manifest "
            f"is missing: {manifest_path}"
        ),
    )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    output_path = (
        PROJECT_DIRECTORY
        / manifest[
            "outputs"
        ]["geopackage"]
    )

    require(
        output_path.exists(),
        (
            "Grid-feasibility output "
            f"is missing: {output_path}"
        ),
    )

    layers = {
        str(row[0])
        for row
        in pyogrio.list_layers(
            output_path
        )
    }

    expected_layers = {
        "parcel_grid_analysis",
        "scope_transmission_lines",
        "scope_substations",
    }

    require(
        expected_layers.issubset(
            layers
        ),
        (
            "Missing grid-feasibility "
            "layers: "
            + ", ".join(
                sorted(
                    expected_layers
                    - layers
                )
            )
        ),
    )

    parcels = gpd.read_file(
        output_path,
        layer="parcel_grid_analysis",
    )

    lines = gpd.read_file(
        output_path,
        layer="scope_transmission_lines",
    )

    stations = gpd.read_file(
        output_path,
        layer="scope_substations",
    )

    required_columns = {
        "parcel_id",
        "nearest_transmission_distance_m",
        "nearest_transmission_voltage_kv",
        "nearest_transmission_voltage_class",
        "nearest_transmission_owner",
        "nearest_substation_distance_m",
        "nearest_substation_max_voltage_kv",
        "nearest_substation_voltage_class",
        "transmission_within_5km_feature_count",
        "transmission_within_5km_maximum_voltage_kv",
        "substation_within_10km_feature_count",
        "substation_within_10km_maximum_voltage_kv",
        "public_grid_context_class",
        "grid_data_confidence",
        "capacity_status",
        "available_capacity_mw",
        "utility_confirmation_required",
        "interconnection_study_required",
        "electrical_service_feasibility_confirmed",
    }

    missing = (
        required_columns
        - set(parcels.columns)
    )

    require(
        not missing,
        (
            "Parcel grid output is missing: "
            + ", ".join(
                sorted(missing)
            )
        ),
    )

    require(
        not parcels.empty,
        "Parcel grid analysis is empty.",
    )

    require(
        parcels[
            "parcel_id"
        ].is_unique,
        "Parcel IDs are not unique.",
    )

    for name, frame in (
        ("parcels", parcels),
        ("transmission lines", lines),
        ("substations", stations),
    ):
        require(
            frame.geometry.notna().all(),
            f"{name} contains null geometry.",
        )

        require(
            (
                ~frame.geometry.is_empty
            ).all(),
            f"{name} contains empty geometry.",
        )

        require(
            frame.geometry.is_valid.all(),
            f"{name} contains invalid geometry.",
        )

    line_distance = pd.to_numeric(
        parcels[
            "nearest_transmission_distance_m"
        ],
        errors="coerce",
    )

    station_distance = pd.to_numeric(
        parcels[
            "nearest_substation_distance_m"
        ],
        errors="coerce",
    )

    require(
        line_distance.dropna().ge(0).all(),
        "Negative transmission distance exists.",
    )

    require(
        station_distance.dropna().ge(0).all(),
        "Negative substation distance exists.",
    )

    line_voltage = pd.to_numeric(
        parcels[
            "nearest_transmission_voltage_kv"
        ],
        errors="coerce",
    )

    station_voltage = pd.to_numeric(
        parcels[
            "nearest_substation_max_voltage_kv"
        ],
        errors="coerce",
    )

    require(
        line_voltage.dropna()
        .between(
            0,
            1000,
            inclusive="right",
        )
        .all(),
        "Invalid line voltage exists.",
    )

    require(
        station_voltage.dropna()
        .between(
            0,
            1000,
            inclusive="right",
        )
        .all(),
        "Invalid substation voltage exists.",
    )

    require(
        parcels[
            "capacity_status"
        ].eq(
            "UNKNOWN_NOT_IN_PUBLIC_SOURCE"
        ).all(),
        (
            "Available capacity was "
            "incorrectly inferred."
        ),
    )

    require(
        parcels[
            "available_capacity_mw"
        ].isna().all(),
        (
            "A public capacity value was "
            "incorrectly populated."
        ),
    )

    require(
        parcels[
            "utility_confirmation_required"
        ].astype(bool).all(),
        (
            "Utility confirmation is not "
            "required for every parcel."
        ),
    )

    require(
        parcels[
            "interconnection_study_required"
        ].astype(bool).all(),
        (
            "Interconnection study is not "
            "required for every parcel."
        ),
    )

    require(
        (
            ~parcels[
                "electrical_service_feasibility_confirmed"
            ].astype(bool)
        ).all(),
        (
            "Electrical feasibility was "
            "incorrectly confirmed."
        ),
    )

    transmission_coverage = float(
        line_distance.notna().mean()
    )

    substation_coverage = float(
        station_distance.notna().mean()
    )

    require(
        transmission_coverage >= 0.95,
        (
            "Fewer than 95% of parcels "
            "received transmission evidence."
        ),
    )

    require(
        substation_coverage >= 0.95,
        (
            "Fewer than 95% of parcels "
            "received substation evidence."
        ),
    )

    safeguards = manifest[
        "safeguards"
    ]

    require(
        safeguards[
            "capacity_inferred_from_voltage"
        ] is False,
        "Capacity was inferred from voltage.",
    )

    require(
        safeguards[
            "capacity_inferred_from_distance"
        ] is False,
        "Capacity was inferred from distance.",
    )

    print()
    print(
        "PARCEL GRID-FEASIBILITY "
        "REVIEW PASSED"
    )

    print(
        "Scope:",
        options.scope_id,
    )

    print(
        "Parcels:",
        f"{len(parcels):,}",
    )

    print(
        "Transmission evidence coverage:",
        f"{transmission_coverage:.1%}",
    )

    print(
        "Substation evidence coverage:",
        f"{substation_coverage:.1%}",
    )

    print()
    print("Public grid context:")

    print(
        parcels[
            "public_grid_context_class"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print("Nearest-line voltage classes:")

    print(
        parcels[
            "nearest_transmission_voltage_class"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print("Grid-data confidence:")

    print(
        parcels[
            "grid_data_confidence"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Capacity remains UNKNOWN and "
        "requires utility confirmation "
        "and an interconnection study."
    )


if __name__ == "__main__":
    main()
