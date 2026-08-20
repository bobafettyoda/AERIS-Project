from __future__ import annotations

import unittest
from pathlib import Path

from analysis.planning.adapters.factory import adapter_for_jurisdiction
from analysis.planning.adapters.null_adapter import NullPlanningAdapter
from analysis.planning.registry import PlanningRegistry


PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]


class PlanningAdapterTests(unittest.TestCase):
    def test_default_registry_uses_explicit_null_adapter(self) -> None:
        registry = PlanningRegistry(
            PROJECT_DIRECTORY
            / "configs"
            / "planning"
            / "maryland_jurisdictions.yaml"
        )
        adapter = adapter_for_jurisdiction(registry.get("003"))
        self.assertIsInstance(adapter, NullPlanningAdapter)
        self.assertFalse(adapter.available())


if __name__ == "__main__":
    unittest.main()
