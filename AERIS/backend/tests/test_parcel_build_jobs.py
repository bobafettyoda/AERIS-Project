from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from analysis.parcels.build_jobs import ScopeBuildCoordinator


class FakeParcelService:
    def __init__(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self.config = {}

    def build_bbox(self, **kwargs):
        return {"scope": {"scope_id": kwargs.get("scope_name")}}


class FakeArtifactService:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def build(self, **kwargs):
        if self.fail:
            raise RuntimeError("configured failure")
        return {"scope_id": kwargs["scope_id"]}


class ParcelBuildJobTests(unittest.TestCase):
    def wait(self, coordinator: ScopeBuildCoordinator, job_id: str):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = coordinator.get(job_id)
            if job["state"] in {"completed", "partial_failure", "failed"}:
                return job
            time.sleep(0.02)
        self.fail("job did not finish")

    def test_optional_domain_failure_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = ScopeBuildCoordinator(
                parcel_service=FakeParcelService(root),
                envelope_service=FakeArtifactService(),
                grid_service=FakeArtifactService(fail=True),
                planning_service=FakeArtifactService(),
                runtime_directory=root / "runtime",
                max_workers=1,
            )
            job = coordinator.submit_bbox(
                west=-77,
                south=38,
                east=-76,
                north=39,
                scope_name="test-scope",
            )
            finished = self.wait(coordinator, job["job_id"])
            coordinator.shutdown()

            self.assertEqual(finished["state"], "partial_failure")
            self.assertEqual(finished["artifacts"]["parcels"]["state"], "ready")
            self.assertEqual(finished["artifacts"]["grid"]["state"], "failed")
            self.assertEqual(finished["artifacts"]["planning"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
