from __future__ import annotations

from copy import deepcopy

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from analysis.viability.engine import evaluate_candidate_record, evaluate_scope_records
from analysis.fast_viability import (
    detailed_analysis_ids,
    downstream_evidence_required_ids,
    parcel_fast_path_decision,
    potential_assemblage_member_ids,
    pre_infrastructure_rejection_reasons,
)


CONFIG = {
    "parcel_gates": {
        "minimum_contiguous_usable_acres": 25.0,
        "minimum_total_site_acres": 25.0,
        "maximum_mapped_wetland_fraction": 0.10,
        "maximum_steep_slope_fraction": 0.25,
        "reject_public_land": True,
        "reject_institutional_use": True,
        "reject_statewide_hard_excluded": True,
        "allowed_road_access": [
            "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
            "NEAR_MAPPED_PUBLIC_ROAD",
        ],
        "road_access_hold_values": ["ROAD_DATA_UNAVAILABLE"],
    },
    "infrastructure_gates": {
        "accepted_grid_context": [
            "VERY_STRONG_MAPPED_GRID_CONTEXT",
            "STRONG_MAPPED_GRID_CONTEXT",
            "MODERATE_MAPPED_GRID_CONTEXT",
        ],
        "hold_grid_context": ["INSUFFICIENT_MAPPED_GRID_DATA"],
        "reject_grid_context": ["LIMITED_MAPPED_GRID_CONTEXT"],
        "capacity_confirmation_required": True,
        "interconnection_study_required": True,
    },
    "planning_gates": {
        "hold_when_statewide_zoning_unavailable": True,
        "manual_local_verification_required": True,
        "known_blocking_statuses": [],
    },
    "ranking": {
        "physical_site_weight": 0.60,
        "regional_suitability_weight": 0.40,
        "maximum_comparison_candidates": 25,
    },
}


def detailed_record(**overrides):
    record = {
        "candidate_id": "P-1",
        "candidate_kind": "PARCEL",
        "parcel_id": "P-1",
        "public_land_flag": False,
        "institutional_use_flag": False,
        "statewide_hard_excluded": False,
        "candidate_eligible": True,
        "candidate_status": "PROMISING_PRELIMINARY_SITE_FEASIBILITY",
        "largest_contiguous_site_acres": 45.0,
        "final_site_area_acres": 55.0,
        "mapped_wetland_fraction": 0.02,
        "steep_slope_fraction": 0.08,
        "road_access_status": "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        "public_grid_context_class": "STRONG_MAPPED_GRID_CONTEXT",
        "planning_review_status": "LOCAL_REVIEW_REQUIRED",
        "manual_local_verification_required": True,
        "capacity_status": "UNKNOWN_NOT_IN_PUBLIC_SOURCE",
        "utility_confirmation_required": True,
        "interconnection_study_required": True,
        "availability_confirmed": False,
        "site_candidate_score": 0.82,
        "statewide_technical_score": 0.84,
    }
    record.update(overrides)
    return record


def test_authoritative_area_upper_bound_rejects_before_detailed_gis():
    decision = parcel_fast_path_decision(
        record={
            "parcel_id": "small",
            "public_land_flag": False,
            "institutional_use_flag": False,
            "statewide_hard_excluded": False,
        },
        base_total_acres=12.0,
        base_largest_contiguous_acres=9.0,
        viability_config=CONFIG,
    )
    assert decision.terminal_individual_rejection is True
    assert set(decision.rejection_reasons) == {
        "INSUFFICIENT_TOTAL_SITE_ACRES",
        "INSUFFICIENT_CONTIGUOUS_USABLE_ACRES",
    }


def test_public_land_is_authoritative_before_expensive_site_work():
    decision = parcel_fast_path_decision(
        record={"parcel_id": "public", "public_land_flag": True},
        base_total_acres=100.0,
        base_largest_contiguous_acres=90.0,
        viability_config=CONFIG,
    )
    assert decision.terminal_individual_rejection is True
    assert "PUBLIC_LAND" in decision.rejection_reasons


def test_small_connected_parcels_are_preserved_for_possible_assemblage():
    ids = pd.Series(["A", "B", "C", "D"])
    geometries = gpd.GeoSeries(
        [
            box(0, 0, 50, 50),
            box(52, 0, 102, 50),
            box(104, 0, 154, 50),
            box(1000, 0, 1050, 50),
        ],
        crs="EPSG:26985",
    )
    potential = potential_assemblage_member_ids(
        parcel_ids=ids,
        base_geometries=geometries,
        base_area_acres=pd.Series([10.0, 10.0, 10.0, 10.0]),
        public_land=pd.Series([False] * 4),
        institutional_use=pd.Series([False] * 4),
        statewide_hard_excluded=pd.Series([False] * 4),
        adjacency_gap_m=8.0,
        minimum_parcel_site_acres=2.0,
        minimum_viable_total_acres=25.0,
        minimum_parcel_count=2,
    )
    assert potential == {"A", "B", "C"}

    decisions = [
        parcel_fast_path_decision(
            record={"parcel_id": parcel_id},
            base_total_acres=10.0,
            base_largest_contiguous_acres=10.0,
            viability_config=CONFIG,
        )
        for parcel_id in ids
    ]
    detailed = detailed_analysis_ids(
        decisions=decisions,
        potential_assemblage_ids=potential,
    )
    assert detailed == {"A", "B", "C"}


def test_large_scope_fast_path_reduces_detailed_set_without_threshold_change():
    small_count = 4058
    ids = [f"S-{index}" for index in range(small_count)] + ["L-1", "L-2"]
    geometries = [
        box(index * 200.0, 0, index * 200.0 + 20, 20)
        for index in range(small_count)
    ] + [
        box(900000, 0, 900500, 500),
        box(901000, 0, 901500, 500),
    ]
    geo = gpd.GeoSeries(geometries, crs="EPSG:26985")
    areas = pd.Series([1.0] * small_count + [40.0, 40.0])
    potential = potential_assemblage_member_ids(
        parcel_ids=ids,
        base_geometries=geo,
        base_area_acres=areas,
        public_land=pd.Series([False] * len(ids)),
        institutional_use=pd.Series([False] * len(ids)),
        statewide_hard_excluded=pd.Series([False] * len(ids)),
        adjacency_gap_m=8.0,
        minimum_parcel_site_acres=2.0,
        minimum_viable_total_acres=25.0,
        minimum_parcel_count=2,
    )
    decisions = [
        parcel_fast_path_decision(
            record={"parcel_id": parcel_id},
            base_total_acres=float(area),
            base_largest_contiguous_acres=float(area),
            viability_config=CONFIG,
        )
        for parcel_id, area in zip(ids, areas)
    ]
    detailed = detailed_analysis_ids(
        decisions=decisions,
        potential_assemblage_ids=potential,
    )
    assert detailed == {"L-1", "L-2"}
    assert len(detailed) / len(ids) < 0.001


def test_fast_rejection_and_full_evidence_produce_same_viability_decision():
    full = detailed_record(
        largest_contiguous_site_acres=20.0,
        final_site_area_acres=20.0,
    )
    fast = {
        "candidate_id": "P-1",
        "candidate_kind": "PARCEL",
        "parcel_id": "P-1",
        "candidate_eligible": False,
        "fast_path_rejected": True,
        "fast_path_analysis_status": (
            "DETAILED_EVIDENCE_SKIPPED_AFTER_AUTHORITATIVE_REJECTION"
        ),
        "fast_path_rejection_reasons": (
            "INSUFFICIENT_TOTAL_SITE_ACRES;"
            "INSUFFICIENT_CONTIGUOUS_USABLE_ACRES"
        ),
        "availability_confirmed": False,
    }
    full_result = evaluate_candidate_record(full, CONFIG)
    fast_result = evaluate_candidate_record(fast, CONFIG)
    assert full_result["viability_status"] == fast_result["viability_status"] == "REJECTED"
    assert full_result["comparison_eligible"] is fast_result["comparison_eligible"] is False
    assert "INSUFFICIENT_TOTAL_SITE_ACRES" in fast_result["rejection_reasons"]
    assert "INSUFFICIENT_CONTIGUOUS_USABLE_ACRES" in fast_result["rejection_reasons"]
    assert "GRID_CONTEXT_EVIDENCE_INSUFFICIENT" not in fast_result["hold_reasons"]


def test_survivor_still_requires_downstream_grid_and_planning_evidence():
    rejected = detailed_record(
        candidate_id="R",
        parcel_id="R",
        largest_contiguous_site_acres=10.0,
        final_site_area_acres=12.0,
    )
    survivor = detailed_record(candidate_id="V", parcel_id="V")
    ids = downstream_evidence_required_ids(
        records=[rejected, survivor],
        viability_config=CONFIG,
    )
    assert ids == {"V"}
    assert pre_infrastructure_rejection_reasons(
        record=rejected,
        viability_config=CONFIG,
    )


def test_phase2_config_flags_remain_authoritative():
    config = deepcopy(CONFIG)
    config["infrastructure_gates"]["capacity_confirmation_required"] = False
    config["infrastructure_gates"]["interconnection_study_required"] = False
    config["planning_gates"]["manual_local_verification_required"] = False
    result = evaluate_candidate_record(detailed_record(), config)
    assert result["viability_status"] == "VIABLE_SCREENING_CANDIDATE"
    assert "UTILITY_CAPACITY_UNCONFIRMED" not in result["review_reasons"]
    assert "INTERCONNECTION_STUDY_REQUIRED" not in result["review_reasons"]
    assert "LOCAL_PLANNING_VERIFICATION_REQUIRED" not in result["review_reasons"]


def test_scope_decision_counts_remain_authoritative_with_mixed_fast_path_records():
    fast = {
        "candidate_id": "R",
        "parcel_id": "R",
        "fast_path_rejected": True,
        "fast_path_rejection_reasons": "INSUFFICIENT_TOTAL_SITE_ACRES",
    }
    viable = detailed_record(candidate_id="V", parcel_id="V")
    result = evaluate_scope_records([fast, viable], CONFIG)
    assert result["counts"] == {
        "evaluated": 2,
        "comparison_eligible": 1,
        "evidence_hold": 0,
        "rejected": 1,
    }
    assert result["comparison_candidates"][0]["candidate_id"] == "V"
