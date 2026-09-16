from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from analysis.common.io import load_yaml
from analysis.viability.engine import evaluate_candidate_record, evaluate_scope_records


CONFIG = load_yaml(
    Path(__file__).resolve().parents[2]
    / "configs"
    / "viability"
    / "data_center_maryland.yaml"
)


def base_candidate() -> dict:
    return {
        "candidate_id": "P-001",
        "candidate_kind": "PARCEL",
        "parcel_id": "P-001",
        "candidate_eligible": True,
        "candidate_score": 0.82,
        "statewide_technical_score": 0.78,
        "statewide_effective_score": 0.78,
        "statewide_hard_excluded": False,
        "public_land_flag": False,
        "institutional_use_flag": False,
        "largest_contiguous_site_acres": 55.0,
        "final_site_area_acres": 61.0,
        "mapped_wetland_fraction": 0.01,
        "steep_slope_fraction": 0.08,
        "building_reference_fraction": 0.02,
        "road_access_status": "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        "public_grid_context_class": "STRONG_MAPPED_GRID_CONTEXT",
        "grid_data_confidence": "HIGH",
        "capacity_status": "UNKNOWN_NOT_IN_PUBLIC_SOURCE",
        "utility_confirmation_required": True,
        "interconnection_study_required": True,
        "planning_review_status": "LOCAL_ZONING_VERIFICATION_REQUIRED",
        "planning_data_confidence": "MEDIUM",
        "manual_local_verification_required": True,
        "availability_confirmed": False,
        "site_feasibility_class": "STRONG_PRELIMINARY_SITE_FEASIBILITY",
        "redevelopment_burden_class": "LOW_MAPPED_REDEVELOPMENT_BURDEN",
    }


def test_viable_candidate_advances_only_after_gates() -> None:
    result = evaluate_candidate_record(base_candidate(), CONFIG)
    assert result["viability_status"] == "VIABLE_SCREENING_CANDIDATE"
    assert result["comparison_eligible"] is True
    assert result["rejection_reasons"] == []
    assert result["hold_reasons"] == []
    assert "UTILITY_CAPACITY_UNCONFIRMED" in result["review_reasons"]
    assert result["viability_score"] == 0.804


def test_hard_exclusion_blocks_candidate_before_scoring() -> None:
    candidate = base_candidate()
    candidate["statewide_hard_excluded"] = True
    result = evaluate_candidate_record(candidate, CONFIG)
    assert result["viability_status"] == "REJECTED"
    assert result["comparison_eligible"] is False
    assert "REGIONAL_HARD_EXCLUSION" in result["rejection_reasons"]
    assert result["viability_score"] is None


def test_insufficient_contiguous_land_is_explicit_rejection() -> None:
    candidate = base_candidate()
    candidate["largest_contiguous_site_acres"] = 12.0
    candidate["final_site_area_acres"] = 18.0
    result = evaluate_candidate_record(candidate, CONFIG)
    assert result["comparison_eligible"] is False
    assert "INSUFFICIENT_CONTIGUOUS_USABLE_ACRES" in result["rejection_reasons"]
    assert "INSUFFICIENT_TOTAL_SITE_ACRES" in result["rejection_reasons"]


def test_missing_grid_evidence_holds_instead_of_pretending_feasibility() -> None:
    candidate = base_candidate()
    candidate["public_grid_context_class"] = "INSUFFICIENT_MAPPED_GRID_DATA"
    result = evaluate_candidate_record(candidate, CONFIG)
    assert result["viability_status"] == "EVIDENCE_HOLD"
    assert result["comparison_eligible"] is False
    assert "GRID_CONTEXT_EVIDENCE_INSUFFICIENT" in result["hold_reasons"]


def test_limited_grid_context_is_rejected() -> None:
    candidate = base_candidate()
    candidate["public_grid_context_class"] = "LIMITED_MAPPED_GRID_CONTEXT"
    result = evaluate_candidate_record(candidate, CONFIG)
    assert result["viability_status"] == "REJECTED"
    assert "GRID_CONTEXT_BELOW_THRESHOLD" in result["rejection_reasons"]


def test_scope_shortlist_contains_only_viable_candidates() -> None:
    good = base_candidate()
    small = deepcopy(good)
    small["candidate_id"] = "P-002"
    small["parcel_id"] = "P-002"
    small["largest_contiguous_site_acres"] = 5.0
    missing = deepcopy(good)
    missing["candidate_id"] = "P-003"
    missing["parcel_id"] = "P-003"
    missing["road_access_status"] = "ROAD_DATA_UNAVAILABLE"

    result = evaluate_scope_records([small, good, missing], CONFIG)
    assert result["scope_status"] == "VIABLE_CANDIDATES_FOUND"
    assert result["counts"] == {
        "evaluated": 3,
        "comparison_eligible": 1,
        "evidence_hold": 1,
        "rejected": 1,
    }
    assert [item["candidate_id"] for item in result["comparison_candidates"]] == [
        "P-001"
    ]

def test_due_diligence_requirements_respect_viability_config() -> None:
    config = deepcopy(CONFIG)
    config["infrastructure_gates"]["capacity_confirmation_required"] = False
    config["infrastructure_gates"]["interconnection_study_required"] = False
    config["planning_gates"]["manual_local_verification_required"] = False

    result = evaluate_candidate_record(base_candidate(), config)

    assert "UTILITY_CAPACITY_UNCONFIRMED" not in result["review_reasons"]
    assert "INTERCONNECTION_STUDY_REQUIRED" not in result["review_reasons"]
    assert "LOCAL_PLANNING_VERIFICATION_REQUIRED" not in result["review_reasons"]

