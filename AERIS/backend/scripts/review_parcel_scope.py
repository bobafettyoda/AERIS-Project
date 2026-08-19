from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd


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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review a normalized AERIS "
            "parcel scope."
        )
    )

    parser.add_argument(
        "scope_id",
        help=(
            "Parcel scope ID from the "
            "scope manifest."
        ),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    manifest_path = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / "parcels"
        / f"{arguments.scope_id}.json"
    )

    require(
        manifest_path.exists(),
        (
            "Parcel scope manifest does "
            f"not exist: {manifest_path}"
        ),
    )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    parcel_path = (
        PROJECT_DIRECTORY
        / manifest[
            "outputs"
        ]["normalized_parcels"]
    )

    require(
        parcel_path.exists(),
        (
            "Normalized parcel output "
            f"does not exist: {parcel_path}"
        ),
    )

    frame = gpd.read_file(
        parcel_path,
        layer="parcels",
    )

    required_columns = {
        "parcel_id",
        "property_address",
        "parcel_area_acres",
        "geometry_area_acres",
        "land_use_code",
        "land_use_description",
        "zoning_code",
        "public_land_flag",
        "institutional_use_flag",
        "existing_development_indicator",
        "availability_status",
        "availability_reason",
        "availability_confirmed",
        "parcel_data_confidence",
        "statewide_cell_id",
        "statewide_technical_score",
        "statewide_effective_score",
        "statewide_equity_gate",
        "scope_overlap_fraction",
    }

    missing_columns = (
        required_columns
        - set(frame.columns)
    )

    require(
        not missing_columns,
        (
            "Parcel output is missing: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        ),
    )

    require(
        not frame.empty,
        "Parcel scope is empty.",
    )

    require(
        frame[
            "parcel_id"
        ].is_unique,
        "Parcel IDs are not unique.",
    )

    require(
        frame.geometry.notna().all(),
        "Null parcel geometry exists.",
    )

    require(
        (
            ~frame.geometry.is_empty
        ).all(),
        "Empty parcel geometry exists.",
    )

    require(
        frame.geometry.is_valid.all(),
        "Invalid parcel geometry exists.",
    )

    require(
        pd.to_numeric(
            frame[
                "geometry_area_acres"
            ],
            errors="coerce",
        ).gt(0).all(),
        (
            "Parcel geometry acreage must "
            "be positive."
        ),
    )

    require(
        pd.to_numeric(
            frame[
                "scope_overlap_fraction"
            ],
            errors="coerce",
        ).between(
            0,
            1,
            inclusive="both",
        ).all(),
        (
            "Scope overlap fractions are "
            "outside 0–1."
        ),
    )

    require(
        not frame[
            "availability_confirmed"
        ].astype(bool).any(),
        (
            "The parcel pipeline must not "
            "confirm availability."
        ),
    )

    allowed_statuses = {
        "PUBLIC_OR_INSTITUTIONAL",
        "EXISTING_USE_REVIEW_REQUIRED",
        "DATA_INSUFFICIENT",
        "POTENTIAL_FURTHER_REVIEW",
    }

    require(
        set(
            frame[
                "availability_status"
            ].dropna().unique()
        ).issubset(
            allowed_statuses
        ),
        (
            "Unexpected parcel availability "
            "status exists."
        ),
    )

    context_fraction = (
        frame[
            "statewide_cell_id"
        ].notna().mean()
    )

    require(
        context_fraction >= 0.95,
        (
            "Fewer than 95% of parcels "
            "received statewide context."
        ),
    )

    print()
    print(
        "PARCEL SCOPE REVIEW PASSED"
    )

    print(
        "Scope:",
        manifest["scope"][
            "scope_id"
        ],
    )

    print(
        "Parcels:",
        f"{len(frame):,}",
    )

    print(
        "Statewide context coverage:",
        f"{context_fraction:.1%}",
    )

    print()
    print(
        "Availability statuses:"
    )

    print(
        frame[
            "availability_status"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Data confidence:"
    )

    print(
        frame[
            "parcel_data_confidence"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Parcel acreage quantiles:"
    )

    print(
        frame[
            "geometry_area_acres"
        ].quantile(
            [
                0,
                0.10,
                0.25,
                0.50,
                0.75,
                0.90,
                1.0,
            ]
        )
    )


if __name__ == "__main__":
    main()
