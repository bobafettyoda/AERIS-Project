from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


AERIS_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = (
    AERIS_ROOT
    / "data/manifests/"
    "statewide_environmental_constraints.json"
)

GRID_PATH = (
    AERIS_ROOT
    / "data/derived/"
    "maryland_grid_1km_environmental.gpkg"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def find_cell_id_column(
    frame: gpd.GeoDataFrame,
) -> str:
    preferred = [
        "grid_cell_id",
        "cell_id",
        "grid_id",
        "cellid",
    ]

    lowered = {
        str(column).casefold(): str(column)
        for column in frame.columns
    }

    for candidate in preferred:
        if candidate.casefold() in lowered:
            return lowered[
                candidate.casefold()
            ]

    for column in frame.columns:
        name = str(column).casefold()

        if (
            "cell" in name
            and "id" in name
        ):
            return str(column)

    raise RuntimeError(
        "Could not identify the grid-cell ID column."
    )


def as_boolean(
    series: pd.Series,
) -> pd.Series:
    if pd.api.types.is_bool_dtype(
        series
    ):
        return series.fillna(False)

    if pd.api.types.is_numeric_dtype(
        series
    ):
        return (
            series.fillna(0) != 0
        )

    true_values = {
        "1",
        "true",
        "t",
        "yes",
        "y",
    }

    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin(true_values)
    )


def find_flag(
    frame: gpd.GeoDataFrame,
    keyword: str,
) -> str | None:
    for column in frame.columns:
        name = str(column).casefold()

        if (
            keyword in name
            and (
                "excluded" in name
                or "exclusion" in name
            )
        ):
            return str(column)

    return None


def main() -> None:
    require(
        MANIFEST_PATH.exists(),
        f"Missing manifest: {MANIFEST_PATH}",
    )

    require(
        GRID_PATH.exists(),
        f"Missing scored grid: {GRID_PATH}",
    )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    grid_summary = manifest["grid"]

    frame = gpd.read_file(
        GRID_PATH
    )

    expected_count = int(
        grid_summary["cell_count"]
    )

    require(
        len(frame) == expected_count,
        (
            f"Grid row count is {len(frame):,}; "
            f"manifest expects "
            f"{expected_count:,}."
        ),
    )

    cell_id_column = (
        find_cell_id_column(frame)
    )

    require(
        frame[
            cell_id_column
        ].notna().all(),
        "Grid contains missing cell IDs.",
    )

    require(
        frame[
            cell_id_column
        ].is_unique,
        "Grid cell IDs are not unique.",
    )

    require(
        frame.geometry.notna().all(),
        "Grid contains null geometries.",
    )

    require(
        (
            ~frame.geometry.is_empty
        ).all(),
        "Grid contains empty geometries.",
    )

    require(
        frame.geometry.is_valid.all(),
        "Grid contains invalid geometries.",
    )

    score_columns = [
        str(column)
        for column in frame.columns
        if str(column)
        .casefold()
        .endswith("_score")
    ]

    require(
        bool(score_columns),
        "No score columns were found.",
    )

    for column in score_columns:
        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).dropna()

        require(
            (
                values.between(
                    0.0,
                    1.0,
                    inclusive="both",
                )
            ).all(),
            (
                f"{column} contains values "
                "outside 0–1."
            ),
        )

    water_flag = find_flag(
        frame,
        "water",
    )

    protected_flag = find_flag(
        frame,
        "protected",
    )

    hydro_flag = (
        find_flag(
            frame,
            "hydro",
        )
        or find_flag(
            frame,
            "sfha",
        )
        or find_flag(
            frame,
            "flood",
        )
    )

    require(
        water_flag is not None,
        "Could not locate the water-exclusion flag.",
    )

    require(
        protected_flag is not None,
        "Could not locate the protected-land flag.",
    )

    require(
        hydro_flag is not None,
        "Could not locate the flood/SFHA flag.",
    )

    water_excluded = as_boolean(
        frame[water_flag]
    )

    protected_excluded = as_boolean(
        frame[protected_flag]
    )

    hydro_excluded = as_boolean(
        frame[hydro_flag]
    )

    any_environmental = (
        water_excluded
        | protected_excluded
        | hydro_excluded
    )

    observed_counts = {
        "water_excluded_cells": int(
            water_excluded.sum()
        ),
        "protected_excluded_cells": int(
            protected_excluded.sum()
        ),
        "hydro_excluded_cells": int(
            hydro_excluded.sum()
        ),
        "any_environmental_exclusion_cells": int(
            any_environmental.sum()
        ),
    }

    for key, observed in (
        observed_counts.items()
    ):
        expected = int(
            grid_summary[key]
        )

        require(
            observed == expected,
            (
                f"{key}: grid contains "
                f"{observed:,}, but manifest "
                f"reports {expected:,}."
            ),
        )

    require(
        grid_summary[
            "partial_heatmap_only"
        ]
        is True,
        "Environmental output is not marked partial.",
    )

    require(
        grid_summary[
            "missing_criterion"
        ]
        == "climate",
        "Expected climate to be the missing criterion.",
    )

    require(
        abs(
            float(
                grid_summary[
                    "partial_technical_weight_total"
                ]
            )
            - 0.7499
        )
        < 0.0001,
        "Partial technical weight is not 0.7499.",
    )

    require(
        int(
            grid_summary[
                "auto_recommendation_eligible_cells"
            ]
        )
        == 0,
        (
            "Automatic recommendations were enabled "
            "before climate was added."
        ),
    )

    require(
        int(
            grid_summary[
                "exploration_eligible_cells"
            ]
        )
        == 0,
        (
            "Final exploration eligibility was enabled "
            "before climate was added."
        ),
    )

    for label, relative_path in (
        manifest["outputs"].items()
    ):
        output_path = (
            AERIS_ROOT
            / relative_path
        )

        require(
            output_path.exists(),
            (
                f"Manifest output {label!r} "
                f"is missing: {output_path}"
            ),
        )

    known_cell = manifest[
        "known_point_review"
    ][
        "nearest_grid_cell"
    ]

    require(
        known_cell
        in set(
            frame[
                cell_id_column
            ].astype(str)
        ),
        (
            "Known-point review references "
            f"missing grid cell {known_cell!r}."
        ),
    )

    partial_count = int(
        grid_summary[
            "partial_score_statistics"
        ][
            "count"
        ]
    )

    missing_partial_scores = (
        expected_count
        - partial_count
    )

    print()
    print("ENVIRONMENTAL REVIEW PASSED")
    print(
        f"Grid cells: {expected_count:,}"
    )
    print(
        "Environmentally excluded: "
        f"{observed_counts['any_environmental_exclusion_cells']:,}"
    )
    print(
        "Outside environmental exclusions: "
        f"{expected_count - observed_counts['any_environmental_exclusion_cells']:,}"
    )
    print(
        "Cells missing partial scores: "
        f"{missing_partial_scores:,}"
    )
    print(
        "Current output: seven-criterion "
        "exploratory heatmap"
    )
    print(
        "Remaining technical criterion: climate"
    )


if __name__ == "__main__":
    main()
