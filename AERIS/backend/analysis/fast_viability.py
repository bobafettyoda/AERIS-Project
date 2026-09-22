from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import geopandas as gpd
import pandas as pd


@dataclass(frozen=True)
class ParcelFastPathDecision:
    parcel_id: str
    terminal_individual_rejection: bool
    rejection_reasons: tuple[str, ...]
    detailed_individual_analysis_required: bool


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {
        "1",
        "true",
        "t",
        "yes",
        "y",
    }


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def authoritative_upper_bound_reasons(
    *,
    record: dict[str, Any],
    base_total_acres: float | None,
    base_largest_contiguous_acres: float | None,
    viability_config: dict[str, Any],
) -> tuple[str, ...]:
    """Return rejection reasons that are provable before detailed GIS work.

    Development-envelope acreage is an upper bound on the later physical-site
    envelope because wetlands and steep-slope subtraction can only remove land.
    Therefore, if the preliminary envelope is already below an authoritative
    minimum-area gate, detailed site analysis cannot reverse that rejection.
    """

    parcel_gates = viability_config["parcel_gates"]
    reasons: list[str] = []

    if parcel_gates.get("reject_public_land", True) and _bool(
        record.get("public_land_flag")
    ):
        reasons.append("PUBLIC_LAND")

    if parcel_gates.get("reject_institutional_use", True) and _bool(
        record.get("institutional_use_flag")
    ):
        reasons.append("INSTITUTIONAL_USE")

    if parcel_gates.get("reject_statewide_hard_excluded", True) and _bool(
        record.get("statewide_hard_excluded")
    ):
        reasons.append("REGIONAL_HARD_EXCLUSION")

    total = _number(base_total_acres)
    if total is not None and total < float(
        parcel_gates["minimum_total_site_acres"]
    ):
        reasons.append("INSUFFICIENT_TOTAL_SITE_ACRES")

    largest = _number(base_largest_contiguous_acres)
    if largest is not None and largest < float(
        parcel_gates["minimum_contiguous_usable_acres"]
    ):
        reasons.append("INSUFFICIENT_CONTIGUOUS_USABLE_ACRES")

    return tuple(dict.fromkeys(reasons))


def parcel_fast_path_decision(
    *,
    record: dict[str, Any],
    base_total_acres: float | None,
    base_largest_contiguous_acres: float | None,
    viability_config: dict[str, Any],
) -> ParcelFastPathDecision:
    reasons = authoritative_upper_bound_reasons(
        record=record,
        base_total_acres=base_total_acres,
        base_largest_contiguous_acres=base_largest_contiguous_acres,
        viability_config=viability_config,
    )
    return ParcelFastPathDecision(
        parcel_id=str(record.get("parcel_id") or ""),
        terminal_individual_rejection=bool(reasons),
        rejection_reasons=reasons,
        detailed_individual_analysis_required=not reasons,
    )


def potential_assemblage_member_ids(
    *,
    parcel_ids: Iterable[str],
    base_geometries: gpd.GeoSeries,
    base_area_acres: pd.Series,
    public_land: pd.Series,
    institutional_use: pd.Series,
    statewide_hard_excluded: pd.Series,
    adjacency_gap_m: float,
    minimum_parcel_site_acres: float,
    minimum_viable_total_acres: float,
    minimum_parcel_count: int = 2,
) -> set[str]:
    """Return parcels that could still participate in a viable assemblage.

    This is a conservative upper-bound screen. Final site envelopes are subsets
    of the preliminary development envelopes, so parcels that cannot form a
    sufficiently large connected component at this stage cannot become a viable
    assemblage after additional constraints are subtracted.
    """

    ids = pd.Series([str(value) for value in parcel_ids], index=base_geometries.index)
    areas = pd.to_numeric(base_area_acres, errors="coerce").fillna(0.0)
    public_mask = public_land.fillna(False).astype(bool)
    institutional_mask = institutional_use.fillna(False).astype(bool)
    hard_mask = statewide_hard_excluded.fillna(False).astype(bool)

    eligible_mask = (
        areas.ge(float(minimum_parcel_site_acres))
        & ~public_mask
        & ~institutional_mask
        & ~hard_mask
        & base_geometries.notna()
        & ~base_geometries.is_empty
    )

    if int(eligible_mask.sum()) < int(minimum_parcel_count):
        return set()

    frame = gpd.GeoDataFrame(
        {
            "parcel_id": ids.loc[eligible_mask].to_numpy(),
            "base_area_acres": areas.loc[eligible_mask].to_numpy(),
        },
        geometry=base_geometries.loc[eligible_mask].to_numpy(),
        crs=base_geometries.crs,
    ).reset_index(drop=True)

    parent = list(range(len(frame)))
    rank = [0] * len(frame)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            return
        if rank[root_left] < rank[root_right]:
            root_left, root_right = root_right, root_left
        parent[root_right] = root_left
        if rank[root_left] == rank[root_right]:
            rank[root_left] += 1

    spatial_index = frame.sindex
    for index, geometry in frame.geometry.items():
        search_geometry = geometry.buffer(float(adjacency_gap_m))
        for other in spatial_index.query(search_geometry, predicate="intersects"):
            other = int(other)
            if other <= index:
                continue
            if search_geometry.intersects(frame.geometry.iloc[other]):
                union(int(index), other)

    groups: dict[int, list[int]] = {}
    for index in range(len(frame)):
        groups.setdefault(find(index), []).append(index)

    result: set[str] = set()
    for indices in groups.values():
        if len(indices) < int(minimum_parcel_count):
            continue

        # Sum is intentionally an upper bound. If even the sum of preliminary
        # envelopes cannot meet the viability acreage floor, later subtraction
        # cannot make the assemblage viable.
        upper_bound_total = float(
            frame.loc[indices, "base_area_acres"].sum()
        )
        if upper_bound_total < float(minimum_viable_total_acres):
            continue

        result.update(frame.loc[indices, "parcel_id"].astype(str).tolist())

    return result


def detailed_analysis_ids(
    *,
    decisions: Iterable[ParcelFastPathDecision],
    potential_assemblage_ids: set[str],
) -> set[str]:
    """Return parcel IDs that still need detailed physical-site analysis."""

    result = set(potential_assemblage_ids)
    for decision in decisions:
        if decision.detailed_individual_analysis_required:
            result.add(decision.parcel_id)
    return result


def pre_infrastructure_rejection_reasons(
    *,
    record: dict[str, Any],
    viability_config: dict[str, Any],
) -> tuple[str, ...]:
    """Return definitive rejection reasons through the road-access gate.

    This mirrors the Phase 2 parcel/site gates, but intentionally stops before
    public-grid and planning evidence. A non-empty result proves those later
    domains cannot reverse the final REJECTED status.
    """

    parcel = viability_config["parcel_gates"]
    reasons: list[str] = []

    if parcel.get("reject_public_land", True) and _bool(
        record.get("public_land_flag")
    ):
        reasons.append("PUBLIC_LAND")
    if parcel.get("reject_institutional_use", True) and _bool(
        record.get("institutional_use_flag")
    ):
        reasons.append("INSTITUTIONAL_USE")
    if parcel.get("reject_statewide_hard_excluded", True) and _bool(
        record.get("statewide_hard_excluded")
    ):
        reasons.append("REGIONAL_HARD_EXCLUSION")

    existing_eligible = record.get("candidate_eligible")
    if existing_eligible is not None and not _bool(existing_eligible):
        status = str(record.get("candidate_status") or "SITE_PIPELINE_INELIGIBLE").strip()
        reasons.append(status or "SITE_PIPELINE_INELIGIBLE")

    contiguous = _number(record.get("largest_contiguous_site_acres"))
    if (
        contiguous is not None
        and contiguous < float(parcel["minimum_contiguous_usable_acres"])
    ):
        reasons.append("INSUFFICIENT_CONTIGUOUS_USABLE_ACRES")

    total = None
    for key in ("total_site_area_acres", "final_site_area_acres"):
        total = _number(record.get(key))
        if total is not None:
            break
    if total is not None and total < float(parcel["minimum_total_site_acres"]):
        reasons.append("INSUFFICIENT_TOTAL_SITE_ACRES")

    wetland = _number(record.get("mapped_wetland_fraction"))
    if wetland is not None and wetland > float(
        parcel["maximum_mapped_wetland_fraction"]
    ):
        reasons.append("MAPPED_WETLAND_FRACTION_EXCEEDS_THRESHOLD")

    steep = _number(record.get("steep_slope_fraction"))
    if steep is not None and steep > float(
        parcel["maximum_steep_slope_fraction"]
    ):
        reasons.append("STEEP_SLOPE_FRACTION_EXCEEDS_THRESHOLD")

    road = record.get("road_access_status")
    if road is not None:
        road_text = str(road).strip()
        if (
            road_text
            and road_text not in set(parcel.get("road_access_hold_values", []))
            and road_text not in set(parcel.get("allowed_road_access", []))
        ):
            reasons.append("ROAD_ACCESS_SCREEN_FAIL")

    return tuple(dict.fromkeys(reasons))


def downstream_evidence_required_ids(
    *,
    records: Iterable[dict[str, Any]],
    viability_config: dict[str, Any],
) -> set[str]:
    """Return candidate IDs that still require grid/planning evidence."""

    result: set[str] = set()
    for record in records:
        if pre_infrastructure_rejection_reasons(
            record=record,
            viability_config=viability_config,
        ):
            continue
        candidate_id = str(
            record.get("candidate_id")
            or record.get("parcel_id")
            or ""
        ).strip()
        if candidate_id:
            result.add(candidate_id)
    return result
