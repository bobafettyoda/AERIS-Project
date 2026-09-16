from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

import pandas as pd


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {
        "1",
        "true",
        "t",
        "yes",
        "y",
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    result = str(value).strip()
    return result or None


def _candidate_area(record: dict[str, Any]) -> float | None:
    for key in ("total_site_area_acres", "final_site_area_acres"):
        value = _number(record.get(key))
        if value is not None:
            return value
    return None


def evaluate_candidate_record(
    record: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one parcel/site candidate using ordered viability gates.

    Known hard/feasibility failures become rejection reasons. Missing core
    screening evidence becomes a hold. Due-diligence items that public data
    cannot confirm remain review reasons and do not masquerade as approvals.
    """

    parcel = config["parcel_gates"]
    grid = config["infrastructure_gates"]
    planning = config["planning_gates"]
    ranking = config["ranking"]

    rejection_reasons: list[str] = []
    hold_reasons: list[str] = []
    review_reasons: list[str] = []

    if parcel.get("reject_public_land", True) and _bool(
        record.get("public_land_flag")
    ):
        rejection_reasons.append("PUBLIC_LAND")

    if parcel.get("reject_institutional_use", True) and _bool(
        record.get("institutional_use_flag")
    ):
        rejection_reasons.append("INSTITUTIONAL_USE")

    if parcel.get("reject_statewide_hard_excluded", True) and _bool(
        record.get("statewide_hard_excluded")
    ):
        rejection_reasons.append("REGIONAL_HARD_EXCLUSION")

    existing_eligible = record.get("candidate_eligible")
    if existing_eligible is not None and not _bool(existing_eligible):
        reason = _text(record.get("candidate_status")) or "SITE_PIPELINE_INELIGIBLE"
        rejection_reasons.append(reason)

    contiguous = _number(record.get("largest_contiguous_site_acres"))
    if contiguous is None:
        hold_reasons.append("CONTIGUOUS_SITE_AREA_UNAVAILABLE")
    elif contiguous < float(parcel["minimum_contiguous_usable_acres"]):
        rejection_reasons.append("INSUFFICIENT_CONTIGUOUS_USABLE_ACRES")

    total_area = _candidate_area(record)
    if total_area is None:
        hold_reasons.append("TOTAL_SITE_AREA_UNAVAILABLE")
    elif total_area < float(parcel["minimum_total_site_acres"]):
        rejection_reasons.append("INSUFFICIENT_TOTAL_SITE_ACRES")

    wetland = _number(record.get("mapped_wetland_fraction"))
    if wetland is None:
        hold_reasons.append("MAPPED_WETLAND_EVIDENCE_UNAVAILABLE")
    elif wetland > float(parcel["maximum_mapped_wetland_fraction"]):
        rejection_reasons.append("MAPPED_WETLAND_FRACTION_EXCEEDS_THRESHOLD")

    steep = _number(record.get("steep_slope_fraction"))
    if steep is None:
        hold_reasons.append("STEEP_SLOPE_EVIDENCE_UNAVAILABLE")
    elif steep > float(parcel["maximum_steep_slope_fraction"]):
        rejection_reasons.append("STEEP_SLOPE_FRACTION_EXCEEDS_THRESHOLD")

    road = _text(record.get("road_access_status")) or "ROAD_DATA_UNAVAILABLE"
    if road in set(parcel.get("road_access_hold_values", [])):
        hold_reasons.append("ROAD_ACCESS_EVIDENCE_UNAVAILABLE")
    elif road not in set(parcel.get("allowed_road_access", [])):
        rejection_reasons.append("ROAD_ACCESS_SCREEN_FAIL")

    grid_context = _text(record.get("public_grid_context_class"))
    if grid_context in set(grid.get("reject_grid_context", [])):
        rejection_reasons.append("GRID_CONTEXT_BELOW_THRESHOLD")
    elif grid_context in set(grid.get("hold_grid_context", [])) or grid_context is None:
        hold_reasons.append("GRID_CONTEXT_EVIDENCE_INSUFFICIENT")
    elif grid_context not in set(grid.get("accepted_grid_context", [])):
        hold_reasons.append("GRID_CONTEXT_UNRECOGNIZED")

    planning_status = _text(record.get("planning_review_status"))
    if planning_status in set(planning.get("known_blocking_statuses", [])):
        rejection_reasons.append("KNOWN_PLANNING_BLOCK")
    elif (
        planning.get("hold_when_statewide_zoning_unavailable", True)
        and planning_status
        and planning_status.startswith("STATEWIDE_ZONING_UNAVAILABLE")
    ):
        hold_reasons.append("STATEWIDE_ZONING_EVIDENCE_UNAVAILABLE")
    elif planning_status is None:
        hold_reasons.append("PLANNING_CONTEXT_UNAVAILABLE")
    elif (
        bool(planning.get("manual_local_verification_required", True))
        and _bool(record.get("manual_local_verification_required", True))
    ):
        review_reasons.append("LOCAL_PLANNING_VERIFICATION_REQUIRED")

    capacity_confirmation_required = (
        bool(grid.get("capacity_confirmation_required", True))
        and _bool(record.get("utility_confirmation_required", True))
    )
    if (
        capacity_confirmation_required
        and _text(record.get("capacity_status")) != "CONFIRMED"
    ):
        review_reasons.append("UTILITY_CAPACITY_UNCONFIRMED")

    interconnection_study_required = (
        bool(grid.get("interconnection_study_required", True))
        and _bool(record.get("interconnection_study_required", True))
    )
    if interconnection_study_required:
        review_reasons.append("INTERCONNECTION_STUDY_REQUIRED")

    if record.get("availability_confirmed") is not None and not _bool(
        record.get("availability_confirmed")
    ):
        review_reasons.append("PARCEL_AVAILABILITY_UNCONFIRMED")

    rejection_reasons = list(dict.fromkeys(rejection_reasons))
    hold_reasons = list(dict.fromkeys(hold_reasons))
    review_reasons = list(dict.fromkeys(review_reasons))

    if rejection_reasons:
        status = "REJECTED"
        comparison_eligible = False
    elif hold_reasons:
        status = "EVIDENCE_HOLD"
        comparison_eligible = False
    else:
        status = "VIABLE_SCREENING_CANDIDATE"
        comparison_eligible = True

    viability_score: float | None = None
    if comparison_eligible:
        physical = _number(record.get("candidate_score"))
        if physical is None:
            physical = _number(record.get("site_candidate_score"))
        regional = _number(record.get("statewide_technical_score"))

        values: list[tuple[float, float]] = []
        if physical is not None:
            values.append((physical, float(ranking["physical_site_weight"])))
        if regional is not None:
            values.append((regional, float(ranking["regional_suitability_weight"])))
        if values:
            denominator = sum(weight for _, weight in values)
            viability_score = round(
                sum(value * weight for value, weight in values) / denominator,
                6,
            )

    return {
        "candidate_id": str(
            record.get("candidate_id")
            or record.get("parcel_id")
            or ""
        ),
        "candidate_kind": _text(record.get("candidate_kind")) or "PARCEL",
        "parcel_id": _text(record.get("parcel_id")),
        "parcel_count": (
            int(record["parcel_count"])
            if _number(record.get("parcel_count")) is not None
            else None
        ),
        "parcel_ids": _text(record.get("parcel_ids")),
        "assemblage_status": _text(record.get("assemblage_status")),
        "candidate_score": _number(
            record.get("candidate_score", record.get("site_candidate_score"))
        ),
        "viability_score": viability_score,
        "viability_status": status,
        "comparison_eligible": comparison_eligible,
        "rejection_reasons": rejection_reasons,
        "hold_reasons": hold_reasons,
        "review_reasons": review_reasons,
        "site_feasibility_class": _text(record.get("site_feasibility_class")),
        "final_site_area_acres": _number(record.get("final_site_area_acres")),
        "total_site_area_acres": _number(record.get("total_site_area_acres")),
        "largest_contiguous_site_acres": contiguous,
        "road_access_status": road,
        "mapped_wetland_fraction": wetland,
        "steep_slope_fraction": steep,
        "building_reference_fraction": _number(record.get("building_reference_fraction")),
        "redevelopment_burden_class": _text(record.get("redevelopment_burden_class")),
        "regional_technical_score": _number(record.get("statewide_technical_score")),
        "regional_effective_score": _number(record.get("statewide_effective_score")),
        "grid_context_class": grid_context,
        "grid_data_confidence": _text(record.get("grid_data_confidence")),
        "capacity_status": _text(record.get("capacity_status")),
        "planning_review_status": planning_status,
        "planning_data_confidence": _text(record.get("planning_data_confidence")),
        "availability_confirmed": (
            None
            if record.get("availability_confirmed") is None
            else _bool(record.get("availability_confirmed"))
        ),
    }


def evaluate_scope_records(
    records: Iterable[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    evaluated = [evaluate_candidate_record(record, config) for record in records]
    eligible = [item for item in evaluated if item["comparison_eligible"]]
    holds = [item for item in evaluated if item["viability_status"] == "EVIDENCE_HOLD"]
    rejected = [item for item in evaluated if item["viability_status"] == "REJECTED"]

    eligible.sort(
        key=lambda item: (
            item["viability_score"] is not None,
            item["viability_score"] or -1.0,
            item["largest_contiguous_site_acres"] or -1.0,
        ),
        reverse=True,
    )

    maximum = int(config["ranking"]["maximum_comparison_candidates"])
    comparison_candidates = eligible[:maximum]

    rejection_counts = Counter(
        reason for item in rejected for reason in item["rejection_reasons"]
    )
    hold_counts = Counter(reason for item in holds for reason in item["hold_reasons"])
    review_counts = Counter(
        reason for item in evaluated for reason in item["review_reasons"]
    )

    if comparison_candidates:
        scope_status = "VIABLE_CANDIDATES_FOUND"
    elif holds:
        scope_status = "EVIDENCE_HOLD_NO_COMPARISON_CANDIDATES"
    else:
        scope_status = "REJECTED_NO_VIABLE_CANDIDATES"

    return {
        "scope_status": scope_status,
        "counts": {
            "evaluated": len(evaluated),
            "comparison_eligible": len(eligible),
            "evidence_hold": len(holds),
            "rejected": len(rejected),
        },
        "rejection_reason_counts": dict(sorted(rejection_counts.items())),
        "hold_reason_counts": dict(sorted(hold_counts.items())),
        "review_reason_counts": dict(sorted(review_counts.items())),
        "comparison_candidates": comparison_candidates,
        "evaluated_candidates": evaluated,
    }
