from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import make_valid
from shapely.ops import unary_union

from analysis.statewide.climate_final_pipeline import (
    TECHNICAL_CRITERIA,
    coerce_boolean_series,
)
from analysis.statewide.grid_infrastructure_pipeline import (
    StageReporter,
    atomic_write_json,
    file_sha256,
    load_yaml,
    resolve_path,
    summary_statistics,
)
from analysis.statewide.scenario import (
    normalize_weights,
)


MARYLAND_COUNTIES = {
    "001": "Allegany County",
    "003": "Anne Arundel County",
    "005": "Baltimore County",
    "009": "Calvert County",
    "011": "Caroline County",
    "013": "Carroll County",
    "015": "Cecil County",
    "017": "Charles County",
    "019": "Dorchester County",
    "021": "Frederick County",
    "023": "Garrett County",
    "025": "Harford County",
    "027": "Howard County",
    "029": "Kent County",
    "031": "Montgomery County",
    "033": "Prince George's County",
    "035": "Queen Anne's County",
    "037": "St. Mary's County",
    "039": "Somerset County",
    "041": "Talbot County",
    "043": "Washington County",
    "045": "Wicomico County",
    "047": "Worcester County",
    "510": "Baltimore City",
}


class UnionFind:
    def __init__(
        self,
        values: list[int],
    ) -> None:
        self.parent = {
            value: value
            for value in values
        }

        self.rank = {
            value: 0
            for value in values
        }

    def find(
        self,
        value: int,
    ) -> int:
        parent = self.parent[value]

        if parent != value:
            self.parent[value] = (
                self.find(parent)
            )

        return self.parent[value]

    def union(
        self,
        first: int,
        second: int,
    ) -> None:
        first_root = self.find(first)
        second_root = self.find(second)

        if first_root == second_root:
            return

        first_rank = self.rank[
            first_root
        ]

        second_rank = self.rank[
            second_root
        ]

        if first_rank < second_rank:
            self.parent[
                first_root
            ] = second_root

        elif first_rank > second_rank:
            self.parent[
                second_root
            ] = first_root

        else:
            self.parent[
                second_root
            ] = first_root

            self.rank[
                first_root
            ] += 1


def standardize_identifier(
    values: pd.Series,
    width: int,
) -> pd.Series:
    return (
        values.astype("string")
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.strip()
        .str.zfill(width)
    )


def prepare_grid_indices(
    frame: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    result = frame.copy()

    if {
        "row",
        "column",
    }.issubset(result.columns):
        result["row"] = pd.to_numeric(
            result["row"],
            errors="raise",
        ).astype(int)

        result["column"] = pd.to_numeric(
            result["column"],
            errors="raise",
        ).astype(int)

        return result

    pattern = re.compile(
        r"MD1K-R(\d+)-C(\d+)"
    )

    parsed = result[
        "cell_id"
    ].astype(str).str.extract(
        pattern
    )

    if parsed.isna().any().any():
        raise RuntimeError(
            "Grid rows and columns are missing "
            "and could not be parsed from cell_id."
        )

    result["row"] = (
        parsed[0].astype(int)
    )

    result["column"] = (
        parsed[1].astype(int)
    )

    return result


def add_county_fields(
    frame: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    result = frame.copy()

    if "county" in result.columns:
        county_fips = (
            standardize_identifier(
                result["county"],
                3,
            )
        )

    elif "GEOID" in result.columns:
        county_fips = (
            standardize_identifier(
                result["GEOID"],
                11,
            ).str.slice(2, 5)
        )

    else:
        county_fips = pd.Series(
            "UNK",
            index=result.index,
            dtype="string",
        )

    result[
        "audit_county_fips"
    ] = county_fips

    result[
        "audit_county_name"
    ] = county_fips.map(
        MARYLAND_COUNTIES
    ).fillna(
        "Unknown county"
    )

    return result


def connected_component_labels(
    frame: pd.DataFrame,
) -> pd.Series:
    if frame.empty:
        return pd.Series(
            dtype="int64"
        )

    required = {
        "row",
        "column",
    }

    missing = required - set(
        frame.columns
    )

    if missing:
        raise ValueError(
            "Connected-component input "
            "is missing: "
            + ", ".join(sorted(missing))
        )

    indices = [
        int(index)
        for index in frame.index
    ]

    union_find = UnionFind(indices)

    coordinate_to_index: dict[
        tuple[int, int],
        int,
    ] = {}

    for index, row in (
        frame.iterrows()
    ):
        coordinate = (
            int(row["row"]),
            int(row["column"]),
        )

        if coordinate in coordinate_to_index:
            raise RuntimeError(
                "Duplicate grid row/column "
                f"coordinate: {coordinate}"
            )

        coordinate_to_index[
            coordinate
        ] = int(index)

    for (
        coordinate,
        index,
    ) in coordinate_to_index.items():
        row_number, column_number = (
            coordinate
        )

        for neighbor in (
            (
                row_number + 1,
                column_number,
            ),
            (
                row_number,
                column_number + 1,
            ),
        ):
            neighbor_index = (
                coordinate_to_index.get(
                    neighbor
                )
            )

            if neighbor_index is not None:
                union_find.union(
                    index,
                    neighbor_index,
                )

    roots = {
        index: union_find.find(index)
        for index in indices
    }

    ordered_roots = {
        root: number
        for number, root
        in enumerate(
            sorted(set(roots.values())),
            start=1,
        )
    }

    return pd.Series(
        {
            index: ordered_roots[root]
            for index, root
            in roots.items()
        },
        dtype="int64",
    )


def score_band(
    value: float,
    bands: list[dict[str, Any]],
) -> tuple[str, str]:
    for index, band in enumerate(
        bands
    ):
        minimum = float(
            band["minimum"]
        )

        maximum = float(
            band["maximum"]
        )

        is_last = (
            index == len(bands) - 1
        )

        if (
            value >= minimum
            and (
                value < maximum
                or (
                    is_last
                    and value <= maximum
                )
            )
        ):
            return (
                str(band["id"]),
                str(band["label"]),
            )

    return (
        "outside_configured_bands",
        "Outside configured bands",
    )


def eligibility_mask(
    frame: pd.DataFrame,
    *,
    mode_config: dict[str, Any],
    score_column: str,
) -> pd.Series:
    eligibility_column = str(
        mode_config[
            "eligibility_column"
        ]
    )

    if eligibility_column not in frame:
        raise RuntimeError(
            "Grid is missing eligibility column: "
            f"{eligibility_column}"
        )

    score = pd.to_numeric(
        frame[score_column],
        errors="coerce",
    )

    land_fraction = pd.to_numeric(
        frame["land_fraction"],
        errors="coerce",
    )

    return (
        coerce_boolean_series(
            frame[
                eligibility_column
            ]
        )
        & score.between(
            float(
                mode_config[
                    "minimum_score"
                ]
            ),
            float(
                mode_config[
                    "maximum_score"
                ]
            ),
            inclusive="both",
        )
        & land_fraction.ge(
            float(
                mode_config[
                    "minimum_land_fraction"
                ]
            )
        )
    )


def build_candidate_zones(
    frame: gpd.GeoDataFrame,
    *,
    mode_name: str,
    mode_config: dict[str, Any],
    rank_config: dict[str, Any],
    bands: list[dict[str, Any]],
    score_column: str = (
        "technical_suitability_score"
    ),
) -> tuple[
    gpd.GeoDataFrame,
    pd.DataFrame,
]:
    candidate_mask = eligibility_mask(
        frame,
        mode_config=mode_config,
        score_column=score_column,
    )

    candidate = frame.loc[
        candidate_mask
    ].copy()

    if candidate.empty:
        return (
            gpd.GeoDataFrame(
                columns=[
                    "zone_id",
                    "geometry",
                ],
                geometry="geometry",
                crs=frame.crs,
            ),
            pd.DataFrame(
                columns=[
                    "mode",
                    "zone_id",
                    "cell_id",
                ]
            ),
        )

    candidate[
        "_component"
    ] = connected_component_labels(
        candidate
    )

    rank_weights = {
        name: float(value)
        for name, value
        in rank_config.items()
    }

    if abs(
        sum(rank_weights.values())
        - 1.0
    ) > 0.000001:
        raise RuntimeError(
            "Zone rank weights must total 1.0."
        )

    minimum_cells = int(
        mode_config[
            "minimum_zone_cells"
        ]
    )

    minimum_area = float(
        mode_config[
            "minimum_zone_area_sq_km"
        ]
    )

    zone_records: list[
        dict[str, Any]
    ] = []

    component_cells: dict[
        int,
        list[str],
    ] = {}

    for component, group in (
        candidate.groupby(
            "_component",
            sort=True,
        )
    ):
        cell_count = len(group)

        area_sq_km = float(
            pd.to_numeric(
                group[
                    "clipped_area_sq_km"
                ],
                errors="coerce",
            ).sum()
        )

        if (
            cell_count < minimum_cells
            or area_sq_km < minimum_area
        ):
            continue

        score_values = pd.to_numeric(
            group[score_column],
            errors="coerce",
        )

        mean_score = float(
            score_values.mean()
        )

        p90_score = float(
            score_values.quantile(
                0.90
            )
        )

        maximum_score = float(
            score_values.max()
        )

        minimum_score = float(
            score_values.min()
        )

        rank_score = (
            mean_score
            * rank_weights[
                "mean_score"
            ]
            + p90_score
            * rank_weights[
                "p90_score"
            ]
            + maximum_score
            * rank_weights[
                "maximum_score"
            ]
        )

        geometry = unary_union(
            list(group.geometry)
        )

        if not geometry.is_valid:
            geometry = make_valid(
                geometry
            )

        anchor = (
            group.assign(
                _zone_score=(
                    score_values
                )
            )
            .sort_values(
                [
                    "_zone_score",
                    "land_fraction",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .iloc[0]
        )

        county_areas = (
            group.groupby(
                [
                    "audit_county_fips",
                    "audit_county_name",
                ],
                dropna=False,
            )[
                "clipped_area_sq_km"
            ]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        county_names = [
            str(index[1])
            for index in (
                county_areas.index
            )
        ]

        dominant_county = (
            county_names[0]
            if county_names
            else "Unknown county"
        )

        equity_counts = (
            group[
                "equity_gate"
            ]
            .astype(str)
            .value_counts()
            .to_dict()
        )

        band_id, band_label = (
            score_band(
                mean_score,
                bands,
            )
        )

        zone_records.append(
            {
                "_component": int(
                    component
                ),
                "mode": mode_name,
                "candidate_label": (
                    "Regional screening "
                    "candidate zone"
                ),
                "cell_count": (
                    cell_count
                ),
                "area_sq_km": round(
                    area_sq_km,
                    3,
                ),
                "mean_score": round(
                    mean_score,
                    6,
                ),
                "median_score": round(
                    float(
                        score_values.median()
                    ),
                    6,
                ),
                "p90_score": round(
                    p90_score,
                    6,
                ),
                "maximum_score": round(
                    maximum_score,
                    6,
                ),
                "minimum_score": round(
                    minimum_score,
                    6,
                ),
                "zone_rank_score": round(
                    rank_score,
                    6,
                ),
                "score_band_id": (
                    band_id
                ),
                "score_band_label": (
                    band_label
                ),
                "anchor_cell_id": str(
                    anchor["cell_id"]
                ),
                "anchor_x_m": float(
                    anchor[
                        "analysis_x_m"
                    ]
                ),
                "anchor_y_m": float(
                    anchor[
                        "analysis_y_m"
                    ]
                ),
                "anchor_longitude": float(
                    anchor[
                        "analysis_lon"
                    ]
                ),
                "anchor_latitude": float(
                    anchor[
                        "analysis_lat"
                    ]
                ),
                "dominant_county": (
                    dominant_county
                ),
                "counties": "; ".join(
                    county_names
                ),
                "equity_gate_summary": (
                    "; ".join(
                        (
                            f"{key}="
                            f"{value}"
                        )
                        for key, value
                        in sorted(
                            equity_counts.items()
                        )
                    )
                ),
                "geometry": geometry,
            }
        )

        component_cells[
            int(component)
        ] = (
            group[
                "cell_id"
            ]
            .astype(str)
            .tolist()
        )

    if not zone_records:
        return (
            gpd.GeoDataFrame(
                columns=[
                    "zone_id",
                    "geometry",
                ],
                geometry="geometry",
                crs=frame.crs,
            ),
            pd.DataFrame(
                columns=[
                    "mode",
                    "zone_id",
                    "cell_id",
                ]
            ),
        )

    zones = gpd.GeoDataFrame(
        zone_records,
        geometry="geometry",
        crs=frame.crs,
    ).sort_values(
        [
            "zone_rank_score",
            "area_sq_km",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)

    prefix = (
        "AUTO"
        if mode_name == "auto"
        else "EXP"
    )

    zones["zone_id"] = [
        f"{prefix}-Z{index:03d}"
        for index in range(
            1,
            len(zones) + 1,
        )
    ]

    component_to_zone = {
        int(row["_component"]): str(
            row["zone_id"]
        )
        for _, row in zones.iterrows()
    }

    membership_rows: list[
        dict[str, Any]
    ] = []

    for (
        component,
        cell_ids,
    ) in component_cells.items():
        zone_id = (
            component_to_zone.get(
                component
            )
        )

        if zone_id is None:
            continue

        membership_rows.extend(
            {
                "mode": mode_name,
                "zone_id": zone_id,
                "cell_id": cell_id,
            }
            for cell_id in cell_ids
        )

    membership = pd.DataFrame(
        membership_rows
    )

    zones = zones.drop(
        columns=[
            "_component",
        ]
    )

    return (
        zones,
        membership,
    )


def select_spaced_zones(
    zones: gpd.GeoDataFrame,
    *,
    top_n: int,
    minimum_spacing_m: float,
) -> gpd.GeoDataFrame:
    if zones.empty:
        return zones.copy()

    selected_indices: list[int] = []
    selected_coordinates: list[
        tuple[float, float]
    ] = []

    ordered = zones.sort_values(
        "zone_rank_score",
        ascending=False,
    )

    for index, zone in (
        ordered.iterrows()
    ):
        x_value = float(
            zone["anchor_x_m"]
        )

        y_value = float(
            zone["anchor_y_m"]
        )

        far_enough = all(
            math.hypot(
                x_value - selected_x,
                y_value - selected_y,
            )
            >= float(
                minimum_spacing_m
            )
            for (
                selected_x,
                selected_y,
            )
            in selected_coordinates
        )

        if not far_enough:
            continue

        selected_indices.append(
            int(index)
        )

        selected_coordinates.append(
            (
                x_value,
                y_value,
            )
        )

        if len(
            selected_indices
        ) >= int(top_n):
            break

    selected = zones.loc[
        selected_indices
    ].copy().reset_index(
        drop=True
    )

    selected[
        "selection_rank"
    ] = range(
        1,
        len(selected) + 1,
    )

    selected["top3"] = (
        selected[
            "selection_rank"
        ].le(3)
    )

    selected["top5"] = (
        selected[
            "selection_rank"
        ].le(5)
    )

    return selected


def score_with_weights(
    frame: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    normalized = normalize_weights(
        weights,
        criteria=tuple(
            TECHNICAL_CRITERIA
        ),
    )

    weighted_sum = pd.Series(
        0.0,
        index=frame.index,
        dtype=float,
    )

    complete = pd.Series(
        True,
        index=frame.index,
        dtype=bool,
    )

    for (
        criterion,
        score_column,
    ) in TECHNICAL_CRITERIA.items():
        values = pd.to_numeric(
            frame[score_column],
            errors="coerce",
        )

        complete &= values.notna()

        weighted_sum += (
            values.fillna(0.0)
            * normalized[
                criterion
            ]
        )

    return weighted_sum.where(
        complete
    )


def select_spaced_cells(
    frame: pd.DataFrame,
    *,
    score: pd.Series,
    minimum_score: float,
    top_n: int,
    minimum_spacing_m: float,
) -> pd.DataFrame:
    eligible = (
        coerce_boolean_series(
            frame[
                "auto_screen_eligible"
            ]
        )
        & score.ge(
            float(minimum_score)
        )
    )

    candidates = (
        frame.loc[
            eligible
        ]
        .copy()
    )

    candidates[
        "_scenario_score"
    ] = score.loc[
        candidates.index
    ]

    candidates = (
        candidates.sort_values(
            "_scenario_score",
            ascending=False,
        )
    )

    selected_indices: list[int] = []

    selected_coordinates: list[
        tuple[float, float]
    ] = []

    for index, candidate in (
        candidates.iterrows()
    ):
        x_value = float(
            candidate[
                "analysis_x_m"
            ]
        )

        y_value = float(
            candidate[
                "analysis_y_m"
            ]
        )

        if not all(
            math.hypot(
                x_value - selected_x,
                y_value - selected_y,
            )
            >= float(
                minimum_spacing_m
            )
            for (
                selected_x,
                selected_y,
            )
            in selected_coordinates
        ):
            continue

        selected_indices.append(
            int(index)
        )

        selected_coordinates.append(
            (
                x_value,
                y_value,
            )
        )

        if len(
            selected_indices
        ) >= int(top_n):
            break

    return candidates.loc[
        selected_indices
    ].copy()


def build_sensitivity_selections(
    frame: pd.DataFrame,
    *,
    decision_model: dict[str, Any],
    sensitivity_config: dict[str, Any],
) -> pd.DataFrame:
    baseline_weights = {
        criterion: float(
            decision_model[
                "criteria"
            ][criterion]["weight"]
        )
        for criterion
        in TECHNICAL_CRITERIA
    }

    scenarios: dict[
        str,
        dict[str, float],
    ] = {
        "baseline": normalize_weights(
            baseline_weights,
            criteria=tuple(
                TECHNICAL_CRITERIA
            ),
        )
    }

    multiplier = float(
        sensitivity_config[
            "criterion_multiplier"
        ]
    )

    for criterion in (
        TECHNICAL_CRITERIA
    ):
        modified = dict(
            baseline_weights
        )

        modified[criterion] *= (
            multiplier
        )

        scenarios[
            f"boost_{criterion}"
        ] = normalize_weights(
            modified,
            criteria=tuple(
                TECHNICAL_CRITERIA
            ),
        )

    if bool(
        sensitivity_config.get(
            "include_equal_weights",
            False,
        )
    ):
        scenarios["equal_weights"] = (
            normalize_weights(
                {
                    criterion: 1.0
                    for criterion
                    in TECHNICAL_CRITERIA
                },
                criteria=tuple(
                    TECHNICAL_CRITERIA
                ),
            )
        )

    records: list[
        dict[str, Any]
    ] = []

    for (
        scenario_name,
        weights,
    ) in scenarios.items():
        scenario_score = (
            score_with_weights(
                frame,
                weights,
            )
        )

        selected = (
            select_spaced_cells(
                frame,
                score=scenario_score,
                minimum_score=float(
                    sensitivity_config[
                        "minimum_score"
                    ]
                ),
                top_n=int(
                    sensitivity_config[
                        "top_n"
                    ]
                ),
                minimum_spacing_m=float(
                    sensitivity_config[
                        "minimum_spacing_m"
                    ]
                ),
            )
        )

        for rank, (
            index,
            row,
        ) in enumerate(
            selected.iterrows(),
            start=1,
        ):
            record = {
                "scenario": (
                    scenario_name
                ),
                "rank": rank,
                "cell_id": str(
                    row["cell_id"]
                ),
                "score": round(
                    float(
                        scenario_score.loc[
                            index
                        ]
                    ),
                    6,
                ),
                "county_fips": str(
                    row[
                        "audit_county_fips"
                    ]
                ),
                "county_name": str(
                    row[
                        "audit_county_name"
                    ]
                ),
                "equity_gate": str(
                    row["equity_gate"]
                ),
            }

            for indicator in (
                "ej_percentile",
                "pollution_burden_percentile",
                "environmental_effects_percentile",
                "sensitive_populations_percentile",
                "minority_or_hispanic_pct",
                "low_income_pct",
                "limited_english_pct",
            ):
                value = row.get(
                    indicator
                )

                record[indicator] = (
                    None
                    if pd.isna(value)
                    else float(value)
                )

            records.append(record)

    return pd.DataFrame(
        records,
        columns=[
            "scenario",
            "rank",
            "cell_id",
            "score",
            "county_fips",
            "county_name",
            "equity_gate",
            "ej_percentile",
            "pollution_burden_percentile",
            "environmental_effects_percentile",
            "sensitive_populations_percentile",
            "minority_or_hispanic_pct",
            "low_income_pct",
            "limited_english_pct",
        ],
    )


def weighted_mean(
    values: pd.Series,
    weights: pd.Series,
) -> float | None:
    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    weight = pd.to_numeric(
        weights,
        errors="coerce",
    )

    valid = (
        numeric.notna()
        & weight.notna()
        & weight.gt(0)
    )

    if not valid.any():
        return None

    return float(
        np.average(
            numeric.loc[valid],
            weights=weight.loc[valid],
        )
    )


def weighted_variance(
    values: pd.Series,
    weights: pd.Series,
) -> float | None:
    mean = weighted_mean(
        values,
        weights,
    )

    if mean is None:
        return None

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    weight = pd.to_numeric(
        weights,
        errors="coerce",
    )

    valid = (
        numeric.notna()
        & weight.notna()
        & weight.gt(0)
    )

    return float(
        np.average(
            (
                numeric.loc[valid]
                - mean
            )
            ** 2,
            weights=weight.loc[valid],
        )
    )


def weighted_share(
    condition: pd.Series,
    weights: pd.Series,
) -> float | None:
    weight = pd.to_numeric(
        weights,
        errors="coerce",
    )

    valid = (
        condition.notna()
        & weight.notna()
        & weight.gt(0)
    )

    if not valid.any():
        return None

    total = float(
        weight.loc[valid].sum()
    )

    if total <= 0:
        return None

    selected = float(
        weight.loc[
            valid
            & condition.fillna(False)
        ].sum()
    )

    return selected / total


def indicator_audit(
    reference: pd.DataFrame,
    selected: pd.DataFrame,
    *,
    column: str,
    label: str,
    threshold: float,
    disparity_config: dict[str, Any],
    minimum_selected_cells: int,
) -> dict[str, Any]:
    if column not in reference:
        return {
            "column": column,
            "label": label,
            "status": (
                "INSUFFICIENT_DATA"
            ),
            "reason": (
                "indicator column missing"
            ),
            "flagged": False,
        }

    reference_values = pd.to_numeric(
        reference[column],
        errors="coerce",
    )

    selected_values = pd.to_numeric(
        selected[column],
        errors="coerce",
    )

    reference_weights = pd.to_numeric(
        reference[
            "clipped_area_sq_km"
        ],
        errors="coerce",
    )

    selected_weights = pd.to_numeric(
        selected[
            "clipped_area_sq_km"
        ],
        errors="coerce",
    )

    selected_valid_count = int(
        selected_values.notna().sum()
    )

    selected_missing_fraction = (
        float(
            selected_values.isna().mean()
        )
        if len(selected_values) > 0
        else 1.0
    )

    reference_mean = weighted_mean(
        reference_values,
        reference_weights,
    )

    selected_mean = weighted_mean(
        selected_values,
        selected_weights,
    )

    reference_variance = (
        weighted_variance(
            reference_values,
            reference_weights,
        )
    )

    selected_variance = (
        weighted_variance(
            selected_values,
            selected_weights,
        )
    )

    reference_share = (
        weighted_share(
            reference_values.ge(
                float(threshold)
            ),
            reference_weights,
        )
    )

    selected_share = (
        weighted_share(
            selected_values.ge(
                float(threshold)
            ),
            selected_weights,
        )
    )

    if (
        reference_share is None
        or selected_share is None
    ):
        representation_ratio = None
        percentage_point_difference = None

    else:
        percentage_point_difference = (
            selected_share
            - reference_share
        ) * 100

        if reference_share == 0:
            representation_ratio = (
                math.inf
                if selected_share > 0
                else 1.0
            )
        else:
            representation_ratio = (
                selected_share
                / reference_share
            )

    if (
        reference_mean is None
        or selected_mean is None
        or reference_variance is None
        or selected_variance is None
    ):
        standardized_mean_difference = (
            None
        )

    else:
        pooled_standard_deviation = (
            math.sqrt(
                (
                    reference_variance
                    + selected_variance
                )
                / 2
            )
        )

        if pooled_standard_deviation == 0:
            standardized_mean_difference = (
                0.0
                if selected_mean
                == reference_mean
                else math.inf
            )
        else:
            standardized_mean_difference = (
                (
                    selected_mean
                    - reference_mean
                )
                / pooled_standard_deviation
            )

    ratio_threshold = float(
        disparity_config[
            "representation_ratio"
        ]
    )

    point_threshold = float(
        disparity_config[
            "percentage_point_difference"
        ]
    )

    mean_threshold = float(
        disparity_config[
            "standardized_mean_difference"
        ]
    )

    ratio_flag = bool(
        representation_ratio
        is not None
        and percentage_point_difference
        is not None
        and representation_ratio
        >= ratio_threshold
        and percentage_point_difference
        >= point_threshold
    )

    mean_flag = bool(
        standardized_mean_difference
        is not None
        and standardized_mean_difference
        >= mean_threshold
    )

    sufficient_sample = (
        selected_valid_count
        >= int(
            minimum_selected_cells
        )
    )

    return {
        "column": column,
        "label": label,
        "threshold": (
            float(threshold)
        ),
        "status": (
            "COMPLETE"
            if sufficient_sample
            else "INSUFFICIENT_DATA"
        ),
        "reference_weighted_mean": (
            reference_mean
        ),
        "selected_weighted_mean": (
            selected_mean
        ),
        "reference_share_at_or_above_threshold": (
            reference_share
        ),
        "selected_share_at_or_above_threshold": (
            selected_share
        ),
        "representation_ratio": (
            representation_ratio
        ),
        "percentage_point_difference": (
            percentage_point_difference
        ),
        "standardized_mean_difference": (
            standardized_mean_difference
        ),
        "selected_valid_cell_count": (
            selected_valid_count
        ),
        "selected_missing_fraction": (
            selected_missing_fraction
        ),
        "ratio_flag": ratio_flag,
        "mean_difference_flag": (
            mean_flag
        ),
        "flagged": bool(
            sufficient_sample
            and (
                ratio_flag
                or mean_flag
            )
        ),
    }


def county_concentration_audit(
    reference: pd.DataFrame,
    selected: pd.DataFrame,
    *,
    concentration_config: dict[str, Any],
) -> dict[str, Any]:
    reference_area = (
        reference.groupby(
            [
                "audit_county_fips",
                "audit_county_name",
            ]
        )[
            "clipped_area_sq_km"
        ].sum()
    )

    selected_area = (
        selected.groupby(
            [
                "audit_county_fips",
                "audit_county_name",
            ]
        )[
            "clipped_area_sq_km"
        ].sum()
    )

    reference_total = float(
        reference_area.sum()
    )

    selected_total = float(
        selected_area.sum()
    )

    rows: list[
        dict[str, Any]
    ] = []

    all_counties = sorted(
        set(reference_area.index)
        | set(selected_area.index)
    )

    for county_key in all_counties:
        reference_value = float(
            reference_area.get(
                county_key,
                0.0,
            )
        )

        selected_value = float(
            selected_area.get(
                county_key,
                0.0,
            )
        )

        reference_share = (
            reference_value
            / reference_total
            if reference_total > 0
            else 0.0
        )

        selected_share = (
            selected_value
            / selected_total
            if selected_total > 0
            else 0.0
        )

        if reference_share == 0:
            location_quotient = (
                math.inf
                if selected_share > 0
                else 1.0
            )
        else:
            location_quotient = (
                selected_share
                / reference_share
            )

        flagged = bool(
            selected_share
            >= float(
                concentration_config[
                    "selected_county_share"
                ]
            )
            and location_quotient
            >= float(
                concentration_config[
                    "county_location_quotient"
                ]
            )
        )

        rows.append(
            {
                "county_fips": str(
                    county_key[0]
                ),
                "county_name": str(
                    county_key[1]
                ),
                "reference_area_share": (
                    reference_share
                ),
                "selected_area_share": (
                    selected_share
                ),
                "location_quotient": (
                    location_quotient
                ),
                "flagged": flagged,
            }
        )

    rows.sort(
        key=lambda row: (
            row[
                "selected_area_share"
            ]
        ),
        reverse=True,
    )

    return {
        "counties": rows,
        "flagged_counties": [
            row
            for row in rows
            if row["flagged"]
        ],
        "flagged": any(
            row["flagged"]
            for row in rows
        ),
    }


def sensitivity_concentration_audit(
    reference: pd.DataFrame,
    selections: pd.DataFrame,
    *,
    concentration_config: dict[str, Any],
) -> dict[str, Any]:
    if selections.empty:
        return {
            "status": (
                "INSUFFICIENT_DATA"
            ),
            "flagged": False,
            "reason": (
                "no sensitivity selections"
            ),
        }

    selection_counts = (
        selections[
            "county_fips"
        ]
        .astype(str)
        .value_counts()
    )

    total_selections = int(
        selection_counts.sum()
    )

    reference_area = (
        reference.groupby(
            "audit_county_fips"
        )[
            "clipped_area_sq_km"
        ].sum()
    )

    reference_total = float(
        reference_area.sum()
    )

    rows: list[
        dict[str, Any]
    ] = []

    for county_fips, count in (
        selection_counts.items()
    ):
        selection_share = (
            int(count)
            / total_selections
        )

        reference_share = (
            float(
                reference_area.get(
                    county_fips,
                    0.0,
                )
            )
            / reference_total
            if reference_total > 0
            else 0.0
        )

        if reference_share == 0:
            location_quotient = (
                math.inf
            )
        else:
            location_quotient = (
                selection_share
                / reference_share
            )

        flagged = bool(
            selection_share
            >= float(
                concentration_config[
                    "selected_county_share"
                ]
            )
            and location_quotient
            >= float(
                concentration_config[
                    "county_location_quotient"
                ]
            )
        )

        rows.append(
            {
                "county_fips": (
                    str(county_fips)
                ),
                "county_name": (
                    MARYLAND_COUNTIES.get(
                        str(county_fips),
                        "Unknown county",
                    )
                ),
                "selection_count": (
                    int(count)
                ),
                "selection_share": (
                    selection_share
                ),
                "reference_area_share": (
                    reference_share
                ),
                "location_quotient": (
                    location_quotient
                ),
                "flagged": flagged,
            }
        )

    rows.sort(
        key=lambda row: (
            row["selection_count"]
        ),
        reverse=True,
    )

    return {
        "status": "COMPLETE",
        "scenario_count": int(
            selections[
                "scenario"
            ].nunique()
        ),
        "selection_count": (
            total_selections
        ),
        "counties": rows,
        "flagged_counties": [
            row
            for row in rows
            if row["flagged"]
        ],
        "flagged": any(
            row["flagged"]
            for row in rows
        ),
    }


def cells_for_zones(
    frame: pd.DataFrame,
    membership: pd.DataFrame,
    zone_ids: set[str],
) -> pd.DataFrame:
    selected_ids = set(
        membership.loc[
            membership[
                "zone_id"
            ].isin(zone_ids),
            "cell_id",
        ].astype(str)
    )

    return frame.loc[
        frame[
            "cell_id"
        ].astype(str).isin(
            selected_ids
        )
    ].copy()


def build_bias_audit(
    *,
    frame: pd.DataFrame,
    auto_membership: pd.DataFrame,
    top_zones: gpd.GeoDataFrame,
    sensitivity_selections: pd.DataFrame,
    audit_config: dict[str, Any],
    release_config: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    complete = coerce_boolean_series(
        frame[
            "technical_score_complete"
        ]
    )

    land_pass = (
        coerce_boolean_series(
            frame[
                "regional_land_threshold_pass"
            ]
        )
    )

    hard_excluded = (
        coerce_boolean_series(
            frame["hard_excluded"]
        )
    )

    reference = frame.loc[
        complete
        & land_pass
        & ~hard_excluded
    ].copy()

    pool_zone_ids = set(
        auto_membership[
            "zone_id"
        ].astype(str)
    )

    candidate_pool = cells_for_zones(
        frame,
        auto_membership,
        pool_zone_ids,
    )

    top_zone_ids = set(
        top_zones[
            "zone_id"
        ].astype(str)
    )

    selected = cells_for_zones(
        frame,
        auto_membership,
        top_zone_ids,
    )

    minimum_selected_cells = int(
        audit_config[
            "minimum_selected_cells"
        ]
    )

    maximum_missing_fraction = float(
        audit_config[
            "maximum_selected_missing_fraction"
        ]
    )

    disparity_config = audit_config[
        "disparity_thresholds"
    ]

    indicator_results = []

    pool_indicator_results = []

    missing_columns = []

    for indicator in audit_config[
        "indicators"
    ]:
        column = str(
            indicator["column"]
        )

        if column not in frame:
            missing_columns.append(
                column
            )

        indicator_results.append(
            indicator_audit(
                reference,
                selected,
                column=column,
                label=str(
                    indicator["label"]
                ),
                threshold=float(
                    indicator[
                        "threshold"
                    ]
                ),
                disparity_config=(
                    disparity_config
                ),
                minimum_selected_cells=(
                    minimum_selected_cells
                ),
            )
        )

        pool_indicator_results.append(
            indicator_audit(
                reference,
                candidate_pool,
                column=column,
                label=str(
                    indicator["label"]
                ),
                threshold=float(
                    indicator[
                        "threshold"
                    ]
                ),
                disparity_config=(
                    disparity_config
                ),
                minimum_selected_cells=(
                    minimum_selected_cells
                ),
            )
        )

    top_county_audit = (
        county_concentration_audit(
            reference,
            selected,
            concentration_config=(
                audit_config[
                    "concentration_thresholds"
                ]
            ),
        )
    )

    pool_county_audit = (
        county_concentration_audit(
            reference,
            candidate_pool,
            concentration_config=(
                audit_config[
                    "concentration_thresholds"
                ]
            ),
        )
    )

    sensitivity_audit = (
        sensitivity_concentration_audit(
            reference,
            sensitivity_selections,
            concentration_config=(
                audit_config[
                    "concentration_thresholds"
                ]
            ),
        )
    )

    selected_gate_counts = (
        selected[
            "equity_gate"
        ].astype(str)
        .value_counts()
        .to_dict()
    )

    selected_missing_excess = [
        result["column"]
        for result in indicator_results
        if float(
            result.get(
                "selected_missing_fraction",
                1.0,
            )
        )
        > maximum_missing_fraction
    ]

    insufficient_indicators = [
        result["column"]
        for result in indicator_results
        if result["status"]
        == "INSUFFICIENT_DATA"
    ]

    disparity_flags = [
        result["column"]
        for result in indicator_results
        if result.get("flagged")
    ]

    pool_disparity_flags = [
        result["column"]
        for result in pool_indicator_results
        if result.get("flagged")
    ]

    blocked_equity_present = any(
        gate in selected_gate_counts
        for gate in (
            "HIGH_BURDEN",
            "INSUFFICIENT_DATA",
        )
    )

    data_complete = bool(
        len(selected)
        >= minimum_selected_cells
        and not missing_columns
        and not selected_missing_excess
        and not insufficient_indicators
    )

    material_flags = {
        "top_zone_disparities": (
            disparity_flags
        ),
        "candidate_pool_disparities": (
            pool_disparity_flags
        ),
        "top_zone_county_concentration": (
            top_county_audit[
                "flagged"
            ]
        ),
        "candidate_pool_county_concentration": (
            pool_county_audit[
                "flagged"
            ]
        ),
        "sensitivity_county_concentration": (
            sensitivity_audit.get(
                "flagged",
                False,
            )
        ),
        "blocked_equity_gate_present": (
            blocked_equity_present
        ),
    }

    any_material_flag = bool(
        disparity_flags
        or pool_disparity_flags
        or top_county_audit[
            "flagged"
        ]
        or pool_county_audit[
            "flagged"
        ]
        or sensitivity_audit.get(
            "flagged",
            False,
        )
        or blocked_equity_present
    )

    if not data_complete:
        audit_status = (
            "INSUFFICIENT_DATA"
        )

    elif any_material_flag:
        audit_status = "FLAGGED"

    else:
        audit_status = "PASS"

    shortlist_ready = bool(
        audit_status == "PASS"
        and len(top_zones)
        >= int(
            release_config[
                "minimum_top_zones"
            ]
        )
    )

    if audit_status == "PASS":
        release_status = (
            "REGIONAL_SCREENING_"
            "SHORTLIST_READY"
        )

    elif audit_status == "FLAGGED":
        release_status = (
            "REVIEW_REQUIRED"
        )

    else:
        release_status = (
            "INSUFFICIENT_DATA"
        )

    return {
        "schema_version": 1,
        "audit": (
            "statewide_disparate_outcome_"
            "and_concentration"
        ),
        "audit_status": audit_status,
        "release_status": release_status,
        "screening_shortlist_ready": (
            shortlist_ready
        ),
        "automated_recommendation_ready": (
            False
        ),
        "technical_score_uses_demographics": (
            False
        ),
        "reference_cohort": (
            audit_config[
                "reference_cohort"
            ]
        ),
        "selected_cohort": (
            audit_config[
                "selected_cohort"
            ]
        ),
        "counts": {
            "reference_cells": (
                len(reference)
            ),
            "candidate_pool_cells": (
                len(candidate_pool)
            ),
            "top_zone_cells": (
                len(selected)
            ),
            "top_zone_count": (
                len(top_zones)
            ),
            "sensitivity_scenarios": (
                int(
                    sensitivity_selections[
                        "scenario"
                    ].nunique()
                )
                if not sensitivity_selections.empty
                else 0
            ),
            "sensitivity_selections": (
                len(
                    sensitivity_selections
                )
            ),
        },
        "selected_equity_gate_counts": (
            selected_gate_counts
        ),
        "data_completeness": {
            "complete": data_complete,
            "missing_columns": (
                missing_columns
            ),
            "selected_missing_excess": (
                selected_missing_excess
            ),
            "insufficient_indicators": (
                insufficient_indicators
            ),
        },
        "top_zone_indicator_audits": (
            indicator_results
        ),
        "candidate_pool_indicator_audits": (
            pool_indicator_results
        ),
        "top_zone_county_concentration": (
            top_county_audit
        ),
        "candidate_pool_county_concentration": (
            pool_county_audit
        ),
        "weight_sensitivity_concentration": (
            sensitivity_audit
        ),
        "material_flags": (
            material_flags
        ),
        "limitations": limitations,
    }


def build_band_summary(
    frame: pd.DataFrame,
    *,
    auto_zones: gpd.GeoDataFrame,
    exploration_zones: gpd.GeoDataFrame,
    bands: list[dict[str, Any]],
) -> dict[str, Any]:
    auto_eligible = (
        coerce_boolean_series(
            frame[
                "auto_screen_eligible"
            ]
        )
    )

    exploration_eligible = (
        coerce_boolean_series(
            frame[
                "exploration_screen_eligible"
            ]
        )
    )

    score = pd.to_numeric(
        frame[
            "technical_suitability_score"
        ],
        errors="coerce",
    )

    summaries = []

    for index, band in enumerate(
        bands
    ):
        minimum = float(
            band["minimum"]
        )

        maximum = float(
            band["maximum"]
        )

        is_last = (
            index == len(bands) - 1
        )

        score_mask = (
            score.ge(minimum)
            & (
                score.lt(maximum)
                if not is_last
                else score.le(maximum)
            )
        )

        auto_cells = frame.loc[
            auto_eligible
            & score_mask
        ]

        exploration_cells = (
            frame.loc[
                exploration_eligible
                & score_mask
            ]
        )

        summaries.append(
            {
                "id": str(
                    band["id"]
                ),
                "label": str(
                    band["label"]
                ),
                "minimum": minimum,
                "maximum": maximum,
                "auto_cell_count": (
                    len(auto_cells)
                ),
                "auto_area_sq_km": (
                    round(
                        float(
                            auto_cells[
                                "clipped_area_sq_km"
                            ].sum()
                        ),
                        3,
                    )
                ),
                "auto_zone_count": (
                    int(
                        auto_zones[
                            "mean_score"
                        ].between(
                            minimum,
                            maximum,
                            inclusive=(
                                "both"
                                if is_last
                                else "left"
                            ),
                        ).sum()
                    )
                    if not auto_zones.empty
                    else 0
                ),
                "exploration_cell_count": (
                    len(
                        exploration_cells
                    )
                ),
                "exploration_area_sq_km": (
                    round(
                        float(
                            exploration_cells[
                                "clipped_area_sq_km"
                            ].sum()
                        ),
                        3,
                    )
                ),
                "exploration_zone_count": (
                    int(
                        exploration_zones[
                            "mean_score"
                        ].between(
                            minimum,
                            maximum,
                            inclusive=(
                                "both"
                                if is_last
                                else "left"
                            ),
                        ).sum()
                    )
                    if not exploration_zones.empty
                    else 0
                ),
            }
        )

    return {
        "schema_version": 1,
        "score_bands": summaries,
        "interpretation": {
            "auto": (
                "Equity PASS, complete, "
                "nonexcluded cells meeting "
                "the land threshold."
            ),
            "exploration": (
                "Equity PASS or CAUTION, "
                "complete, nonexcluded cells "
                "meeting the land threshold."
            ),
            "70_to_90": (
                "Exploratory range intended "
                "to identify potentially "
                "improvable or lower-competition "
                "regional opportunities."
            ),
        },
    }


def write_zone_file(
    zones: gpd.GeoDataFrame,
    path: Path,
    layer: str,
) -> None:
    if zones.empty:
        raise RuntimeError(
            f"No candidate zones were produced "
            f"for {path.name}."
        )

    output = zones.copy()

    output.geometry = (
        output.geometry.make_valid()
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        path.unlink()

    output.to_file(
        path,
        layer=layer,
        driver="GPKG",
        index=False,
    )


def build_candidate_zones_and_audit(
    config_path: Path,
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

    final_grid_path = resolve_path(
        project_directory,
        inputs[
            "final_grid"
        ]["path"],
    )

    decision_model_path = (
        resolve_path(
            project_directory,
            inputs[
                "decision_model"
            ]["path"],
        )
    )

    final_manifest_path = (
        resolve_path(
            project_directory,
            inputs[
                "final_model_manifest"
            ]["path"],
        )
    )

    for path in (
        final_grid_path,
        decision_model_path,
        final_manifest_path,
    ):
        if not path.exists():
            raise RuntimeError(
                "Required input is missing: "
                f"{path}"
            )

    reporter = StageReporter(
        total_stages=8
    )

    reporter.stage(
        1,
        "Loading complete statewide model",
    )

    frame = gpd.read_file(
        final_grid_path,
        layer=inputs[
            "final_grid"
        ]["layer"],
    )

    frame = (
        prepare_grid_indices(
            frame
        )
    )

    frame = add_county_fields(
        frame
    )

    if not frame[
        "cell_id"
    ].is_unique:
        raise RuntimeError(
            "Final grid cell IDs "
            "are not unique."
        )

    final_manifest = json.loads(
        final_manifest_path
        .read_text(
            encoding="utf-8"
        )
    )

    decision_model = load_yaml(
        decision_model_path
    )

    if (
        final_manifest[
            "final_model"
        ][
            "complete_cells"
        ]
        <= 0
    ):
        raise RuntimeError(
            "Final statewide model has "
            "no complete cells."
        )

    reporter.detail(
        f"{len(frame):,} statewide cells"
    )

    zone_config = config[
        "zone_build"
    ]

    bands = config[
        "score_bands"
    ]

    reporter.stage(
        2,
        "Building baseline auto-screen zones",
    )

    (
        auto_zones,
        auto_membership,
    ) = build_candidate_zones(
        frame,
        mode_name="auto",
        mode_config=(
            zone_config["auto"]
        ),
        rank_config=(
            zone_config[
                "rank_weights"
            ]
        ),
        bands=bands,
    )

    reporter.detail(
        (
            f"{len(auto_zones):,} "
            "contiguous auto-screen zones"
        )
    )

    reporter.stage(
        3,
        "Building 70–90 exploration zones",
    )

    (
        exploration_zones,
        exploration_membership,
    ) = build_candidate_zones(
        frame,
        mode_name=(
            "exploration"
        ),
        mode_config=(
            zone_config[
                "exploration"
            ]
        ),
        rank_config=(
            zone_config[
                "rank_weights"
            ]
        ),
        bands=bands,
    )

    reporter.detail(
        (
            f"{len(exploration_zones):,} "
            "contiguous exploration zones"
        )
    )

    reporter.stage(
        4,
        "Selecting geographically "
        "separated top zones",
    )

    top_zones = select_spaced_zones(
        auto_zones,
        top_n=int(
            zone_config[
                "auto"
            ]["top_n"]
        ),
        minimum_spacing_m=float(
            zone_config[
                "auto"
            ][
                "minimum_zone_spacing_m"
            ]
        ),
    )

    reporter.detail(
        (
            f"{len(top_zones):,} "
            "top zones selected"
        )
    )

    reporter.stage(
        5,
        "Running technical-weight "
        "sensitivity scenarios",
    )

    sensitivity_selections = (
        build_sensitivity_selections(
            frame,
            decision_model=(
                decision_model
            ),
            sensitivity_config=(
                config[
                    "bias_audit"
                ]["sensitivity"]
            ),
        )
    )

    reporter.detail(
        (
            f"{sensitivity_selections['scenario'].nunique():,} "
            "weight scenarios"
        )
    )

    reporter.detail(
        (
            f"{len(sensitivity_selections):,} "
            "spatially separated "
            "sensitivity selections"
        )
    )

    reporter.stage(
        6,
        "Running disparate-outcome "
        "and concentration audit",
    )

    audit = build_bias_audit(
        frame=frame,
        auto_membership=(
            auto_membership
        ),
        top_zones=top_zones,
        sensitivity_selections=(
            sensitivity_selections
        ),
        audit_config=(
            config["bias_audit"]
        ),
        release_config=(
            config["release"]
        ),
        limitations=list(
            config["limitations"]
        ),
    )

    reporter.detail(
        (
            "Audit status: "
            f"{audit['audit_status']}"
        )
    )

    reporter.detail(
        (
            "Release status: "
            f"{audit['release_status']}"
        )
    )

    top_zones[
        "bias_audit_status"
    ] = audit[
        "audit_status"
    ]

    top_zones[
        "screening_shortlist_ready"
    ] = audit[
        "screening_shortlist_ready"
    ]

    top_zones[
        "automated_recommendation_ready"
    ] = False

    top_zones[
        "required_next_review"
    ] = (
        "Parcel, zoning, utility, "
        "engineering, environmental, "
        "and community due diligence"
    )

    reporter.stage(
        7,
        "Writing candidate-zone outputs",
    )

    auto_output = resolve_path(
        project_directory,
        outputs[
            "auto_zones"
        ]["path"],
    )

    exploration_output = (
        resolve_path(
            project_directory,
            outputs[
                "exploration_zones"
            ]["path"],
        )
    )

    top_output = resolve_path(
        project_directory,
        outputs[
            "top_zones"
        ]["path"],
    )

    membership_output = (
        resolve_path(
            project_directory,
            outputs[
                "zone_membership"
            ]["path"],
        )
    )

    write_zone_file(
        auto_zones,
        auto_output,
        outputs[
            "auto_zones"
        ]["layer"],
    )

    write_zone_file(
        exploration_zones,
        exploration_output,
        outputs[
            "exploration_zones"
        ]["layer"],
    )

    top_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if top_output.exists():
        top_output.unlink()

    top_zones.to_crs(
        "EPSG:4326"
    ).to_file(
        top_output,
        driver="GeoJSON",
        index=False,
    )

    membership_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    membership = pd.concat(
        [
            auto_membership,
            exploration_membership,
        ],
        ignore_index=True,
    )

    membership.to_csv(
        membership_output,
        index=False,
    )

    band_summary = (
        build_band_summary(
            frame,
            auto_zones=auto_zones,
            exploration_zones=(
                exploration_zones
            ),
            bands=bands,
        )
    )

    band_output = resolve_path(
        project_directory,
        outputs[
            "score_band_summary"
        ]["path"],
    )

    audit_output = resolve_path(
        project_directory,
        outputs[
            "bias_audit"
        ]["path"],
    )

    atomic_write_json(
        band_output,
        band_summary,
    )

    atomic_write_json(
        audit_output,
        audit,
    )

    reporter.detail(
        str(auto_output)
    )

    reporter.detail(
        str(exploration_output)
    )

    reporter.detail(
        str(top_output)
    )

    reporter.stage(
        8,
        "Writing candidate-zone manifest",
    )

    auto_top_ids = (
        top_zones[
            "zone_id"
        ].astype(str).tolist()
    )

    manifest = {
        "schema_version": 1,
        "pipeline": (
            "statewide_candidate_zones_"
            "and_bias_audit"
        ),
        "snapshot_label": config[
            "snapshot_label"
        ],
        "input": {
            "final_grid": str(
                final_grid_path
                .relative_to(
                    project_directory
                )
            ),
            "final_grid_sha256": (
                file_sha256(
                    final_grid_path
                )
            ),
            "final_model_manifest": str(
                final_manifest_path
                .relative_to(
                    project_directory
                )
            ),
            "final_model_manifest_sha256": (
                file_sha256(
                    final_manifest_path
                )
            ),
        },
        "zone_method": {
            "adjacency": zone_config[
                "adjacency"
            ],
            "rank_weights": (
                zone_config[
                    "rank_weights"
                ]
            ),
            "auto": zone_config[
                "auto"
            ],
            "exploration": (
                zone_config[
                    "exploration"
                ]
            ),
        },
        "counts": {
            "grid_cells": len(
                frame
            ),
            "auto_zone_count": len(
                auto_zones
            ),
            "exploration_zone_count": (
                len(
                    exploration_zones
                )
            ),
            "top_zone_count": len(
                top_zones
            ),
            "top3_zone_count": int(
                top_zones[
                    "top3"
                ].sum()
            ),
            "top5_zone_count": int(
                top_zones[
                    "top5"
                ].sum()
            ),
            "auto_zone_cell_memberships": (
                len(auto_membership)
            ),
            "exploration_zone_cell_memberships": (
                len(
                    exploration_membership
                )
            ),
        },
        "top_zone_ids": auto_top_ids,
        "top_zone_score_statistics": (
            summary_statistics(
                top_zones[
                    "mean_score"
                ]
            )
        ),
        "top_zone_area_statistics_sq_km": (
            summary_statistics(
                top_zones[
                    "area_sq_km"
                ]
            )
        ),
        "audit": {
            "status": audit[
                "audit_status"
            ],
            "release_status": (
                audit[
                    "release_status"
                ]
            ),
            "screening_shortlist_ready": (
                audit[
                    "screening_shortlist_ready"
                ]
            ),
            "automated_recommendation_ready": (
                False
            ),
            "technical_score_uses_demographics": (
                False
            ),
            "material_flags": (
                audit[
                    "material_flags"
                ]
            ),
        },
        "terminology": {
            "allowed": (
                "Regional screening "
                "candidate zone"
            ),
            "not_yet_allowed": [
                "Recommended build site",
                "Approved development site",
                "Investment-ready parcel",
            ],
        },
        "required_next_stage": [
            "Parcel and contiguous-land analysis",
            "Zoning and land-use compatibility",
            "Wetlands and sensitive receptors",
            "Utility capacity and interconnection study",
            "Ownership and acquisition feasibility",
            "Community engagement and public-health review",
        ],
        "outputs": {
            "auto_zones": str(
                auto_output.relative_to(
                    project_directory
                )
            ),
            "exploration_zones": str(
                exploration_output.relative_to(
                    project_directory
                )
            ),
            "top_zones": str(
                top_output.relative_to(
                    project_directory
                )
            ),
            "zone_membership": str(
                membership_output
                .relative_to(
                    project_directory
                )
            ),
            "score_band_summary": str(
                band_output.relative_to(
                    project_directory
                )
            ),
            "bias_audit": str(
                audit_output.relative_to(
                    project_directory
                )
            ),
        },
        "output_checksums": {
            "auto_zones": (
                file_sha256(
                    auto_output
                )
            ),
            "exploration_zones": (
                file_sha256(
                    exploration_output
                )
            ),
            "top_zones": (
                file_sha256(
                    top_output
                )
            ),
            "zone_membership": (
                file_sha256(
                    membership_output
                )
            ),
            "score_band_summary": (
                file_sha256(
                    band_output
                )
            ),
            "bias_audit": (
                file_sha256(
                    audit_output
                )
            ),
        },
    }

    manifest_output = (
        resolve_path(
            project_directory,
            outputs[
                "manifest"
            ]["path"],
        )
    )

    atomic_write_json(
        manifest_output,
        manifest,
    )

    reporter.detail(
        str(manifest_output)
    )

    return manifest
