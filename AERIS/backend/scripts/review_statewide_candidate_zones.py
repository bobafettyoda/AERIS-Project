from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd


AERIS_ROOT = (
    Path(__file__).resolve().parents[2]
)

AUTO_PATH = (
    AERIS_ROOT
    / "data/derived/"
    "maryland_candidate_zones_auto.gpkg"
)

EXPLORATION_PATH = (
    AERIS_ROOT
    / "data/derived/"
    "maryland_candidate_zones_exploration.gpkg"
)

TOP_PATH = (
    AERIS_ROOT
    / "data/derived/"
    "maryland_candidate_zones_top5.geojson"
)

AUDIT_PATH = (
    AERIS_ROOT
    / "data/manifests/"
    "statewide_bias_audit.json"
)

MANIFEST_PATH = (
    AERIS_ROOT
    / "data/manifests/"
    "statewide_candidate_zones.json"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    for path in (
        AUTO_PATH,
        EXPLORATION_PATH,
        TOP_PATH,
        AUDIT_PATH,
        MANIFEST_PATH,
    ):
        require(
            path.exists(),
            f"Missing output: {path}",
        )

    auto = gpd.read_file(
        AUTO_PATH,
        layer="candidate_zones",
    )

    exploration = gpd.read_file(
        EXPLORATION_PATH,
        layer="candidate_zones",
    )

    top = gpd.read_file(
        TOP_PATH
    ).to_crs(
        auto.crs
    )

    audit = json.loads(
        AUDIT_PATH.read_text(
            encoding="utf-8"
        )
    )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    require(
        not auto.empty,
        "No auto-screen zones were produced.",
    )

    require(
        not exploration.empty,
        "No exploration zones were produced.",
    )

    require(
        not top.empty,
        "No top zones were produced.",
    )

    for name, frame in (
        ("auto", auto),
        (
            "exploration",
            exploration,
        ),
        ("top", top),
    ):
        require(
            frame[
                "zone_id"
            ].is_unique,
            f"{name} zone IDs are not unique.",
        )

        require(
            frame.geometry.notna().all(),
            f"{name} zones contain null geometry.",
        )

        require(
            (
                ~frame.geometry.is_empty
            ).all(),
            f"{name} zones contain empty geometry.",
        )

        require(
            frame.geometry.is_valid.all(),
            f"{name} zones contain invalid geometry.",
        )

        require(
            pd.to_numeric(
                frame[
                    "mean_score"
                ],
                errors="coerce",
            )
            .between(
                0.0,
                1.0,
                inclusive="both",
            )
            .all(),
            f"{name} mean scores are invalid.",
        )

    require(
        len(top)
        <= int(
            manifest[
                "zone_method"
            ]["auto"]["top_n"]
        ),
        "Top-zone count exceeds configured top_n.",
    )

    minimum_spacing = float(
        manifest[
            "zone_method"
        ][
            "auto"
        ][
            "minimum_zone_spacing_m"
        ]
    )

    coordinates = [
        (
            float(row[
                "anchor_x_m"
            ]),
            float(row[
                "anchor_y_m"
            ]),
        )
        for _, row in top.iterrows()
    ]

    for first_index in range(
        len(coordinates)
    ):
        for second_index in range(
            first_index + 1,
            len(coordinates),
        ):
            distance = math.hypot(
                coordinates[
                    first_index
                ][0]
                - coordinates[
                    second_index
                ][0],
                coordinates[
                    first_index
                ][1]
                - coordinates[
                    second_index
                ][1],
            )

            require(
                distance
                >= minimum_spacing
                - 0.001,
                (
                    "Top zones violate the "
                    "minimum-spacing rule."
                ),
            )

    require(
        not top[
            "equity_gate_summary"
        ].astype(str)
        .str.contains(
            "HIGH_BURDEN|INSUFFICIENT_DATA",
            regex=True,
        ).any(),
        (
            "A top auto-screen zone contains "
            "a blocked equity gate."
        ),
    )

    require(
        audit[
            "audit_status"
        ]
        in {
            "PASS",
            "FLAGGED",
            "INSUFFICIENT_DATA",
        },
        "Bias-audit status is invalid.",
    )

    require(
        audit[
            "technical_score_uses_demographics"
        ]
        is False,
        (
            "Audit says demographics entered "
            "the technical score."
        ),
    )

    require(
        audit[
            "automated_recommendation_ready"
        ]
        is False,
        (
            "Automated recommendations were "
            "enabled prematurely."
        ),
    )

    if audit[
        "screening_shortlist_ready"
    ]:
        require(
            audit[
                "audit_status"
            ]
            == "PASS",
            (
                "Shortlist was released without "
                "an audit PASS."
            ),
        )

    require(
        manifest[
            "audit"
        ][
            "automated_recommendation_ready"
        ]
        is False,
        (
            "Manifest enables automated "
            "recommendations."
        ),
    )

    print()
    print(
        "CANDIDATE-ZONE PIPELINE "
        "REVIEW PASSED"
    )

    print(
        f"Auto-screen zones: "
        f"{len(auto):,}"
    )

    print(
        f"Exploration zones: "
        f"{len(exploration):,}"
    )

    print(
        f"Spatially separated top zones: "
        f"{len(top):,}"
    )

    print()
    print(
        "Bias-audit status:",
        audit["audit_status"],
    )

    print(
        "Release status:",
        audit["release_status"],
    )

    print(
        "Screening shortlist ready:",
        audit[
            "screening_shortlist_ready"
        ],
    )

    print(
        "Automated recommendation ready:",
        audit[
            "automated_recommendation_ready"
        ],
    )

    print()
    print("Top zones:")

    print(
        top[
            [
                "selection_rank",
                "zone_id",
                "mean_score",
                "maximum_score",
                "area_sq_km",
                "cell_count",
                "dominant_county",
                "score_band_label",
            ]
        ].sort_values(
            "selection_rank"
        ).to_string(
            index=False
        )
    )

    flagged = audit[
        "material_flags"
    ]

    print()
    print("Material audit flags:")

    print(
        json.dumps(
            flagged,
            indent=2,
        )
    )

    print()
    print(
        "These remain regional screening "
        "zones—not approved or "
        "investment-ready sites."
    )


if __name__ == "__main__":
    main()
