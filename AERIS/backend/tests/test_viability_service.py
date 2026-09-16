from __future__ import annotations

from pathlib import Path

import pytest

from analysis.common.io import load_yaml
from analysis.viability.service import ViabilityService


CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "viability"
    / "data_center_maryland.yaml"
)


class FakeStatewideService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def zone_feature_collection(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "zone_id": "AUTO-Z900",
                        "mean_score": 0.81,
                    },
                }
            ],
            "metadata": {},
        }


class FakePaths:
    def __init__(self) -> None:
        self.output = Path("/missing/output.gpkg")
        self.manifest = Path("/missing/manifest.json")


class FakeSiteService:
    config = {"layers": {"parcel_analysis": "parcel_analysis"}}

    def _paths(self, scope_id: str):
        return FakePaths()


class FakeGridService(FakeSiteService):
    pass


class FakePlanningService:
    config = {"layers": {"parcel_analysis": "parcel_analysis"}}

    def _paths(self, scope_id: str):
        return Path("/missing/planning.gpkg"), Path("/missing/planning.json")


def service() -> ViabilityService:
    return ViabilityService(
        config_path=CONFIG_PATH,
        statewide_service=FakeStatewideService(),
        site_service=FakeSiteService(),
        grid_service=FakeGridService(),
        planning_service=FakePlanningService(),
    )


def test_search_areas_never_applies_fixed_top_n(monkeypatch) -> None:
    subject = service()
    monkeypatch.setattr(
        subject,
        "_artifact_readiness",
        lambda scope_id: {"site": False, "grid": False, "planning": False},
    )

    result = subject.search_areas(mode="auto")

    call = subject.statewide_service.calls[-1]
    assert call["top_n"] is None
    assert call["minimum_score"] == 0.70
    assert result["metadata"]["fixed_top_n"] is False
    feature = result["features"][0]["properties"]
    assert feature["analysis_role"] == "REGIONAL_SEARCH_AREA"
    assert feature["scope_id"] == "zone-auto-z900"
    assert feature["viability_state"] == "NOT_INVESTIGATED"


def test_comparison_refuses_candidate_not_in_viable_shortlist(monkeypatch) -> None:
    subject = service()
    monkeypatch.setattr(
        subject,
        "evaluate_scope",
        lambda **kwargs: {
            "comparison_candidates": [
                {"candidate_id": "P-001", "comparison_eligible": True}
            ]
        },
    )

    with pytest.raises(KeyError):
        subject.compare_candidates(
            scope_id="zone-auto-z900",
            candidate_ids=["P-001", "P-REJECTED"],
        )


def test_comparison_preserves_requested_viable_order(monkeypatch) -> None:
    subject = service()
    monkeypatch.setattr(
        subject,
        "evaluate_scope",
        lambda **kwargs: {
            "comparison_candidates": [
                {"candidate_id": "P-001", "comparison_eligible": True},
                {"candidate_id": "P-002", "comparison_eligible": True},
            ]
        },
    )

    result = subject.compare_candidates(
        scope_id="zone-auto-z900",
        candidate_ids=["P-002", "P-001"],
    )
    assert [item["candidate_id"] for item in result] == ["P-002", "P-001"]
