from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd


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
    parser = argparse.ArgumentParser()

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
        / "parcel_planning_context"
        / f"{options.scope_id}.json"
    )

    require(
        manifest_path.exists(),
        (
            "Planning manifest is missing: "
            f"{manifest_path}"
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

    parcels = gpd.read_file(
        output_path,
        layer=(
            "parcel_planning_analysis"
        ),
    )

    required_columns = {
        "parcel_id",
        "county_fips",
        "county_name",
        "municipality_name",
        "planning_authority_level",
        "planning_authority_name",
        "planning_authority_status",
        "statewide_zoning_status",
        "local_zoning_source_status",
        "comprehensive_plan_source_status",
        "active_development_source_status",
        "permit_source_status",
        "planning_review_status",
        "planning_data_confidence",
        "pfa_status",
        "critical_area_overlap",
        "local_zoning_verified",
        "permitted_use_determined",
        "active_development_clear",
        "permit_clearance_determined",
        "entitlement_clearance_determined",
        "manual_local_verification_required",
    }

    missing = (
        required_columns
        - set(parcels.columns)
    )

    require(
        not missing,
        (
            "Planning output is missing: "
            + ", ".join(
                sorted(missing)
            )
        ),
    )

    require(
        parcels[
            "parcel_id"
        ].is_unique,
        "Parcel IDs are not unique.",
    )

    require(
        parcels[
            "county_fips"
        ].notna().mean()
        >= 0.95,
        (
            "Fewer than 95% of parcels "
            "have county jurisdiction."
        ),
    )

    require(
        parcels[
            "manual_local_verification_required"
        ].astype(bool).all(),
        (
            "Manual local verification "
            "is not required for every parcel."
        ),
    )

    for column in (
        "local_zoning_verified",
        "permitted_use_determined",
        "active_development_clear",
        "permit_clearance_determined",
        "entitlement_clearance_determined",
    ):
        require(
            (
                ~parcels[
                    column
                ].astype(bool)
            ).all(),
            (
                f"{column} was incorrectly "
                "confirmed."
            ),
        )

    safeguards = manifest[
        "safeguards"
    ]

    for key, value in (
        safeguards.items()
    ):
        if key.endswith(
            "_inferred"
        ):
            require(
                value is False,
                (
                    f"Safeguard {key} was "
                    "incorrectly enabled."
                ),
            )

    require(
        manifest[
            "registry_coverage"
        ][
            "jurisdiction_count"
        ]
        == 24,
        (
            "The planning registry does "
            "not contain all 24 jurisdictions."
        ),
    )

    print()
    print(
        "PARCEL PLANNING-CONTEXT "
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

    print()
    print(
        "Planning review statuses:"
    )

    print(
        parcels[
            "planning_review_status"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Planning authorities:"
    )

    print(
        parcels[
            "planning_authority_status"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "Planning data confidence:"
    )

    print(
        parcels[
            "planning_data_confidence"
        ].value_counts(
            dropna=False
        ).to_string()
    )

    print()
    print(
        "No-data is not interpreted "
        "as no restriction."
    )


if __name__ == "__main__":
    main()
