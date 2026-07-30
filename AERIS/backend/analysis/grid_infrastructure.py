from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from analysis.decision_model import DecisionModel
from analysis.distance_criterion import DistanceCriterion


class GridInfrastructureCriterion:
    """Combine substation and transmission proximity into one score."""

    def __init__(
        self,
        transmission_layer_url: str,
        substation_layer_url: str,
    ) -> None:
        self.criterion_name = "grid_infrastructure"
        self.methodology = (
            "composite_substation_transmission_proximity"
        )
        self.model = DecisionModel()

        model_path = (
            Path(__file__).resolve().parents[2]
            / "configs"
            / "decision_models"
            / "data_center_maryland_demo.yaml"
        )

        with model_path.open("r", encoding="utf-8") as file:
            model_config = yaml.safe_load(file)

        scoring = model_config.get(
            "grid_infrastructure_scoring"
        )

        if not scoring:
            raise RuntimeError(
                "grid_infrastructure_scoring is missing "
                "from the decision-model YAML."
            )

        self.methodology = scoring["method"]

        self.substation_component_weight = float(
            scoring["substation_component_weight"]
        )
        self.transmission_component_weight = float(
            scoring["transmission_component_weight"]
        )

        component_total = (
            self.substation_component_weight
            + self.transmission_component_weight
        )

        if abs(component_total - 1.0) > 0.000001:
            raise RuntimeError(
                "Grid component weights must total 1.0."
            )

        self.limitations = list(
            scoring.get("limitations", [])
        )

        self.substation_criterion = DistanceCriterion(
            criterion_name=self.criterion_name,
            source_layer="Electric Substations",
            layer_url=substation_layer_url,
            preferred_distance_key="substation_m",
            search_delta_degrees=0.25,
            result_record_count=500,
        )

        self.transmission_criterion = DistanceCriterion(
            criterion_name=self.criterion_name,
            source_layer=(
                "HIFLD Electric Power Transmission Lines"
            ),
            layer_url=transmission_layer_url,
            preferred_distance_key="transmission_line_m",
            search_delta_degrees=0.25,
            result_record_count=500,
        )

    @staticmethod
    def _component_output(
        result: dict[str, Any],
        component_weight: float,
    ) -> dict[str, Any]:
        return {
            "source_layer": result["source_layer"],
            "nearest_distance_m": result[
                "nearest_distance_m"
            ],
            "features_checked": result[
                "features_checked"
            ],
            "normalized_score": result[
                "normalized_score"
            ],
            "component_weight": component_weight,
            "normalization": result["normalization"],
        }

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        substation = self.substation_criterion.evaluate(
            lat=lat,
            lon=lon,
        )

        transmission = (
            self.transmission_criterion.evaluate(
                lat=lat,
                lon=lon,
            )
        )

        substation_score = float(
            substation["normalized_score"]
        )
        transmission_score = float(
            transmission["normalized_score"]
        )

        normalized_score = round(
            (
                substation_score
                * self.substation_component_weight
            )
            + (
                transmission_score
                * self.transmission_component_weight
            ),
            6,
        )

        contribution = self.model.contribution(
            self.criterion_name,
            normalized_score,
        )

        return {
            "criterion": self.criterion_name,
            "methodology": self.methodology,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "components": {
                "substation_proximity": (
                    self._component_output(
                        substation,
                        self.substation_component_weight,
                    )
                ),
                "transmission_line_proximity": (
                    self._component_output(
                        transmission,
                        self.transmission_component_weight,
                    )
                ),
            },
            "excluded": False,
            "normalized_score": normalized_score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
            "limitations": self.limitations,
        }
