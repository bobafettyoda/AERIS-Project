from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from analysis.parcels.build_jobs import ScopeBuildCoordinator
from analysis.viability.service import ViabilityService


class FakeSiteService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _paths(self, scope_id: str):
        return SimpleNamespace(
            output=self.root / f"{scope_id}-site.gpkg",
            manifest=self.root / f"{scope_id}-site.json",
        )


class FakeGridService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _paths(self, scope_id: str):
        return SimpleNamespace(
            output=self.root / f"{scope_id}-grid.gpkg",
            manifest=self.root / f"{scope_id}-grid.json",
        )


class FakePlanningService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _paths(self, scope_id: str):
        return (
            self.root / f"{scope_id}-planning.gpkg",
            self.root / f"{scope_id}-planning.json",
        )


def write_site_manifest(service: FakeSiteService, scope_id: str, count: int) -> None:
    paths = service._paths(scope_id)
    paths.output.touch()
    paths.manifest.write_text(
        json.dumps(
            {
                "fast_path": {
                    "downstream_evidence_required_count": count,
                    "downstream_candidate_ids": [],
                }
            }
        ),
        encoding="utf-8",
    )


def test_build_coordinator_skips_downstream_when_no_candidate_can_advance(tmp_path):
    site = FakeSiteService(tmp_path)
    write_site_manifest(site, "scope", 0)
    coordinator = ScopeBuildCoordinator.__new__(ScopeBuildCoordinator)
    coordinator.site_service = site
    assert coordinator._downstream_evidence_required("scope") is False


def test_build_coordinator_requires_downstream_for_survivors(tmp_path):
    site = FakeSiteService(tmp_path)
    write_site_manifest(site, "scope", 3)
    coordinator = ScopeBuildCoordinator.__new__(ScopeBuildCoordinator)
    coordinator.site_service = site
    assert coordinator._downstream_evidence_required("scope") is True


def test_viability_readiness_accepts_intentional_downstream_skip(tmp_path):
    site = FakeSiteService(tmp_path)
    write_site_manifest(site, "scope", 0)
    service = ViabilityService.__new__(ViabilityService)
    service.site_service = site
    service.grid_service = FakeGridService(tmp_path)
    service.planning_service = FakePlanningService(tmp_path)
    readiness = service._artifact_readiness("scope")
    assert readiness == {"site": True, "grid": True, "planning": True}


def test_viability_readiness_still_requires_downstream_for_survivors(tmp_path):
    site = FakeSiteService(tmp_path)
    write_site_manifest(site, "scope", 2)
    service = ViabilityService.__new__(ViabilityService)
    service.site_service = site
    service.grid_service = FakeGridService(tmp_path)
    service.planning_service = FakePlanningService(tmp_path)
    readiness = service._artifact_readiness("scope")
    assert readiness == {"site": True, "grid": False, "planning": False}
