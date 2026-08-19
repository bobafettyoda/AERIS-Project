from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pyogrio


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[1]
)

PROJECT_DIRECTORY = (
    BACKEND_DIRECTORY.parent
)

MANIFEST_PATH = (
    PROJECT_DIRECTORY
    / "data"
    / "manifests"
    / "aviation"
    / "faa_nasr_2026-08-06.json"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(
        MANIFEST_PATH.exists(),
        (
            "FAA aviation manifest "
            f"is missing: {MANIFEST_PATH}"
        ),
    )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
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
            "FAA aviation GeoPackage "
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
        "airport_points",
        "runway_centerlines",
        "runway_hard_conflicts",
        "aviation_notice_screening",
    }

    require(
        expected_layers.issubset(
            layers
        ),
        (
            "FAA output is missing layers: "
            + ", ".join(
                sorted(
                    expected_layers
                    - layers
                )
            )
        ),
    )

    airports = gpd.read_file(
        output_path,
        layer="airport_points",
    )

    runways = gpd.read_file(
        output_path,
        layer="runway_centerlines",
    )

    hard = gpd.read_file(
        output_path,
        layer="runway_hard_conflicts",
    )

    review = gpd.read_file(
        output_path,
        layer="aviation_notice_screening",
    )

    for name, frame in (
        ("airports", airports),
        ("runways", runways),
        ("hard conflicts", hard),
        ("notice screening", review),
    ):
        require(
            not frame.empty,
            f"{name} layer is empty.",
        )

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

    require(
        hard.geometry.area.gt(0).all(),
        (
            "Physical runway conflict "
            "contains zero-area geometry."
        ),
    )

    require(
        (
            hard[
                "subtract_from_envelope"
            ].astype(bool)
        ).all(),
        (
            "Physical runway conflicts "
            "are not marked subtractive."
        ),
    )

    require(
        (
            ~review[
                "subtract_from_envelope"
            ].astype(bool)
        ).all(),
        (
            "Part 77 notice screens were "
            "incorrectly marked subtractive."
        ),
    )

    require(
        (
            ~review[
                "proposed_height_evaluated"
            ].astype(bool)
        ).all(),
        (
            "Notice screening incorrectly "
            "claims proposed height was "
            "evaluated."
        ),
    )

    require(
        "BWI"
        in set(
            airports[
                "ARPT_ID"
            ].astype(str)
        ),
        (
            "Baltimore/Washington "
            "International was not found."
        ),
    )

    safeguards = manifest[
        "safeguards"
    ]

    for key in (
        "airport_property_boundaries_included",
        "runway_protection_zones_included",
        "part77_determination_made",
        "proposed_structure_height_evaluated",
        "faa_approval_inferred",
    ):
        require(
            safeguards[key] is False,
            (
                f"FAA safeguard {key} "
                "was incorrectly enabled."
            ),
        )

    print()
    print(
        "FAA AVIATION REVIEW PASSED"
    )

    print(
        "Cycle:",
        manifest["snapshot_label"],
    )

    print(
        "Regional landing facilities:",
        f"{len(airports):,}",
    )

    print(
        "Runway centerlines:",
        f"{len(runways):,}",
    )

    print(
        "Physical runway conflicts:",
        f"{len(hard):,}",
    )

    print(
        "Notice screening features:",
        f"{len(review):,}",
    )

    print()
    print(
        "Runways missing usable width:",
        manifest[
            "diagnostics"
        ][
            "runways_missing_usable_width"
        ],
    )

    print(
        "Incomplete runway-end groups:",
        manifest[
            "diagnostics"
        ][
            "incomplete_endpoint_groups"
        ],
    )

    print()
    print(
        "Physical runway pavement is a "
        "mapped hard conflict. Part 77 "
        "notice screening remains a "
        "height-dependent review overlay."
    )


if __name__ == "__main__":
    main()
