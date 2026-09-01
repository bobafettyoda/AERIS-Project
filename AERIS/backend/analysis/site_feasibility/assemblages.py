from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import GeometryCollection, MultiPolygon, Polygon, make_valid, union_all


class UnionFind:
    def __init__(self, values: list[int]) -> None:
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: int) -> int:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


@dataclass(frozen=True)
class CandidateThresholds:
    strong_largest_acres: float
    strong_maximum_steep_fraction: float
    strong_maximum_wetland_fraction: float
    strong_maximum_building_fraction: float
    strong_road_access: tuple[str, ...]
    promising_largest_acres: float
    promising_maximum_steep_fraction: float
    promising_maximum_wetland_fraction: float
    promising_road_access: tuple[str, ...]
    limited_minimum_acres: float


def polygon_components(geometry) -> list[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    geometry = make_valid(geometry)
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        result: list[Polygon] = []
        for part in geometry.geoms:
            result.extend(polygon_components(part))
        return result
    return []


def largest_component(geometry):
    components = polygon_components(geometry)
    if not components:
        return GeometryCollection()
    return max(components, key=lambda item: item.area)


def stable_assemblage_id(parcel_ids: list[str]) -> str:
    digest = hashlib.sha256(
        "|".join(sorted(parcel_ids)).encode("utf-8")
    ).hexdigest()[:12]
    return f"ASM-{digest.upper()}"


def access_rank(value: str | None) -> int:
    return {
        "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY": 4,
        "NEAR_MAPPED_PUBLIC_ROAD": 3,
        "DISTANT_MAPPED_PUBLIC_ROAD": 2,
        "LIMITED_ACCESS_ROAD_ADJACENCY_REVIEW_REQUIRED": 1,
        "REMOTE_FROM_MAPPED_PUBLIC_ROAD": 1,
        "ROAD_DATA_UNAVAILABLE": 0,
    }.get(str(value or ""), 0)


def right_of_way_indicator(
    *,
    account_id: object,
    parcel_id: object,
) -> bool:
    account = str(
        account_id or ""
    ).strip().upper()

    if account in {
        "ROW",
        "R/W",
        "R-O-W",
        "RIGHT OF WAY",
        "RIGHT-OF-WAY",
    }:
        return True

    parcel_tokens = {
        token
        for token
        in str(
            parcel_id or ""
        ).upper().split("-")
        if token
    }

    return "ROW" in parcel_tokens


def candidate_eligibility(
    *,
    public_land_flag: bool,
    institutional_use_flag: bool,
    statewide_hard_excluded: bool,
    site_feasibility_class: str,
    right_of_way_flag: bool = False,
) -> tuple[bool, str, str]:
    if public_land_flag or institutional_use_flag:
        return (
            False,
            "INELIGIBLE_PUBLIC_OR_INSTITUTIONAL",
            "Parcel attributes indicate public or institutional use.",
        )

    if statewide_hard_excluded:
        return (
            False,
            "INELIGIBLE_REGIONAL_HARD_EXCLUSION",
            "The inherited statewide screening cell is hard excluded.",
        )

    if right_of_way_flag:
        return (
            False,
            "INELIGIBLE_RIGHT_OF_WAY",
            (
                "Parcel identifiers indicate a mapped "
                "right-of-way record rather than an "
                "ordinary developable parcel."
            ),
        )

    if site_feasibility_class == "LIMITED_PHYSICAL_SITE_FEASIBILITY":
        return (
            False,
            "INELIGIBLE_LIMITED_PHYSICAL_SITE",
            "The largest preliminary contiguous site is below the configured minimum.",
        )

    return (
        True,
        "PRELIMINARY_PHYSICAL_COMPARISON_CANDIDATE",
        "No configured public/institutional, statewide hard-exclusion, or minimum-area gate blocks comparison.",
    )


def best_access(values: pd.Series) -> str:
    cleaned = [str(value) for value in values.dropna()]
    if not cleaned:
        return "ROAD_DATA_UNAVAILABLE"
    return max(cleaned, key=access_rank)


def classify_site(
    *,
    largest_contiguous_acres: float,
    steep_fraction: float | None,
    wetland_fraction: float | None,
    building_fraction: float | None,
    road_access_status: str | None,
    thresholds: CandidateThresholds,
) -> str:
    steep = 1.0 if steep_fraction is None else float(steep_fraction)
    wetland = 1.0 if wetland_fraction is None else float(wetland_fraction)
    building = 1.0 if building_fraction is None else float(building_fraction)
    road = str(road_access_status or "ROAD_DATA_UNAVAILABLE")

    if largest_contiguous_acres < thresholds.limited_minimum_acres:
        return "LIMITED_PHYSICAL_SITE_FEASIBILITY"

    if (
        largest_contiguous_acres >= thresholds.strong_largest_acres
        and steep <= thresholds.strong_maximum_steep_fraction
        and wetland <= thresholds.strong_maximum_wetland_fraction
        and building <= thresholds.strong_maximum_building_fraction
        and road in thresholds.strong_road_access
    ):
        return "STRONG_PRELIMINARY_SITE_FEASIBILITY"

    if (
        largest_contiguous_acres >= thresholds.promising_largest_acres
        and steep <= thresholds.promising_maximum_steep_fraction
        and wetland <= thresholds.promising_maximum_wetland_fraction
        and road in thresholds.promising_road_access
    ):
        return "PROMISING_PRELIMINARY_SITE_FEASIBILITY"

    return "PHYSICAL_SITE_REVIEW_REQUIRED"


def transparent_candidate_score(
    *,
    largest_contiguous_acres: float,
    steep_fraction: float | None,
    wetland_fraction: float | None,
    building_fraction: float | None,
    road_access_status: str | None,
) -> float:
    area_score = min(max(largest_contiguous_acres / 100.0, 0.0), 1.0)
    access_score = access_rank(road_access_status) / 4.0
    slope_score = 0.0 if steep_fraction is None else 1.0 - min(max(steep_fraction, 0.0), 1.0)
    wetland_score = 0.0 if wetland_fraction is None else 1.0 - min(max(wetland_fraction, 0.0), 1.0)
    development_score = 0.0 if building_fraction is None else 1.0 - min(max(building_fraction, 0.0), 1.0)
    return round(
        0.35 * area_score
        + 0.20 * access_score
        + 0.15 * slope_score
        + 0.15 * wetland_score
        + 0.15 * development_score,
        6,
    )


def build_assemblages(
    *,
    parcel_analysis: gpd.GeoDataFrame,
    site_envelopes: gpd.GeoDataFrame,
    square_meters_per_acre: float,
    adjacency_gap_m: float,
    minimum_parcel_site_acres: float,
    minimum_total_site_acres: float,
    minimum_parcel_count: int,
    maximum_parcel_count: int,
    maximum_candidates: int,
    thresholds: CandidateThresholds,
) -> gpd.GeoDataFrame:
    if site_envelopes.empty:
        return gpd.GeoDataFrame(
            {"assemblage_id": [], "geometry": []},
            geometry="geometry",
            crs=parcel_analysis.crs,
        )

    attributes = parcel_analysis.drop(columns="geometry").copy()
    candidates = site_envelopes.merge(
        attributes,
        how="left",
        on="parcel_id",
        validate="one_to_one",
    )
    candidates = candidates.loc[
        pd.to_numeric(
            candidates["final_site_area_acres"],
            errors="coerce",
        ).fillna(0).ge(minimum_parcel_site_acres)
        & ~candidates["public_land_flag"].fillna(False).astype(bool)
        & ~candidates["institutional_use_flag"].fillna(False).astype(bool)
        & ~candidates.get(
            "statewide_hard_excluded",
            pd.Series(False, index=candidates.index),
        ).fillna(False).astype(bool)
        & ~candidates.get(
            "right_of_way_flag",
            pd.Series(False, index=candidates.index),
        ).fillna(False).astype(bool)
    ].copy()
    candidates = candidates.reset_index(drop=True)
    if len(candidates) < minimum_parcel_count:
        return gpd.GeoDataFrame(
            {"assemblage_id": [], "geometry": []},
            geometry="geometry",
            crs=parcel_analysis.crs,
        )

    union_find = UnionFind(list(candidates.index))
    spatial_index = candidates.sindex
    for index, geometry in candidates.geometry.items():
        search_geometry = geometry.buffer(adjacency_gap_m)
        for other in spatial_index.query(search_geometry, predicate="intersects"):
            other = int(other)
            if other <= index:
                continue
            if search_geometry.intersects(candidates.geometry.iloc[other]):
                union_find.union(index, other)

    groups: dict[int, list[int]] = {}
    for index in candidates.index:
        groups.setdefault(union_find.find(index), []).append(index)

    records: list[dict[str, Any]] = []
    for indices in groups.values():
        if len(indices) < minimum_parcel_count:
            continue
        group = candidates.loc[indices].copy()
        parcel_ids = sorted(group["parcel_id"].astype(str).tolist())
        geometry = union_all(list(group.geometry))
        geometry = make_valid(geometry)
        largest = largest_component(geometry)
        total_site_acres = float(geometry.area / square_meters_per_acre)
        largest_site_acres = float(largest.area / square_meters_per_acre)
        if total_site_acres < minimum_total_site_acres:
            continue

        parcel_count = len(parcel_ids)
        oversize = parcel_count > maximum_parcel_count
        weights = pd.to_numeric(
            group["final_site_area_acres"],
            errors="coerce",
        ).fillna(0)
        weight_total = float(weights.sum())

        def weighted(column: str) -> float | None:
            values = pd.to_numeric(group[column], errors="coerce")
            valid = values.notna() & weights.gt(0)
            if not valid.any():
                return None
            return float(np.average(values[valid], weights=weights[valid]))

        steep_fraction = weighted("steep_slope_fraction")
        wetland_fraction = weighted("mapped_wetland_fraction")
        building_fraction = weighted("building_reference_fraction")
        road_status = best_access(group["road_access_status"])
        site_class = classify_site(
            largest_contiguous_acres=largest_site_acres,
            steep_fraction=steep_fraction,
            wetland_fraction=wetland_fraction,
            building_fraction=building_fraction,
            road_access_status=road_status,
            thresholds=thresholds,
        )
        score = transparent_candidate_score(
            largest_contiguous_acres=largest_site_acres,
            steep_fraction=steep_fraction,
            wetland_fraction=wetland_fraction,
            building_fraction=building_fraction,
            road_access_status=road_status,
        )
        candidate_is_eligible = (
            site_class != "LIMITED_PHYSICAL_SITE_FEASIBILITY"
        )
        records.append(
            {
                "evidence_kind": "SITE_ASSEMBLAGE",
                "candidate_kind": "MULTI_PARCEL_ASSEMBLAGE",
                "candidate_id": stable_assemblage_id(parcel_ids),
                "assemblage_id": stable_assemblage_id(parcel_ids),
                "parcel_count": parcel_count,
                "parcel_ids": ";".join(parcel_ids),
                "total_site_area_acres": round(total_site_acres, 6),
                "largest_contiguous_site_acres": round(largest_site_acres, 6),
                "component_count": len(polygon_components(geometry)),
                "road_access_status": road_status,
                "steep_slope_fraction": steep_fraction,
                "mapped_wetland_fraction": wetland_fraction,
                "building_reference_fraction": building_fraction,
                "candidate_score": score,
                "site_feasibility_class": site_class,
                "candidate_eligible": candidate_is_eligible,
                "candidate_status": (
                    "INELIGIBLE_LIMITED_PHYSICAL_SITE"
                    if not candidate_is_eligible
                    else (
                        "PRELIMINARY_ASSEMBLAGE_SIZE_REVIEW_REQUIRED"
                        if oversize
                        else "PRELIMINARY_PHYSICAL_COMPARISON_CANDIDATE"
                    )
                ),
                "candidate_status_reason": (
                    "The assemblage largest contiguous site is below the configured minimum."
                    if not candidate_is_eligible
                    else (
                        "The assemblage exceeds the configured parcel-count review threshold."
                        if oversize
                        else "The assemblage passes configured preliminary physical comparison gates."
                    )
                ),
                "assemblage_status": (
                    "OVERSIZED_ASSEMBLAGE_REVIEW_REQUIRED"
                    if oversize
                    else "PRELIMINARY_ASSEMBLAGE"
                ),
                "parcel_control_confirmed": False,
                "acquisition_feasibility_confirmed": False,
                "geometry": geometry,
            }
        )

    if not records:
        return gpd.GeoDataFrame(
            {"assemblage_id": [], "geometry": []},
            geometry="geometry",
            crs=parcel_analysis.crs,
        )

    frame = gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs=parcel_analysis.crs,
    )
    return frame.sort_values(
        ["candidate_score", "largest_contiguous_site_acres"],
        ascending=[False, False],
    ).head(maximum_candidates).reset_index(drop=True)
