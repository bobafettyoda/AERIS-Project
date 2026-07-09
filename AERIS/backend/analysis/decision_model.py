from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class DecisionModel:
    def __init__(self, model_path: Path | None = None) -> None:
        backend_dir = Path(__file__).resolve().parents[1]
        project_dir = backend_dir.parent

        self.model_path = model_path or (
            project_dir
            / "configs"
            / "decision_models"
            / "data_center_maryland_demo.yaml"
        )
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        with self.model_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def weight(self, criterion_name: str) -> float:
        return float(self.data["criteria"][criterion_name]["weight"])

    def contribution(self, criterion_name: str, score: float) -> dict[str, float]:
        weight = self.weight(criterion_name)
        return {
            "weight": weight,
            "weighted_contribution": round(score * weight, 6),
        }

    def preferred_distance(self, key: str) -> float:
        return float(self.data["preferred_distances"][key])

    def study_area(self) -> dict[str, Any]:
        return self.data["study_area"]

    def grid_resolution_m(self) -> float:
        return float(self.data["analysis"]["grid_resolution_m"])