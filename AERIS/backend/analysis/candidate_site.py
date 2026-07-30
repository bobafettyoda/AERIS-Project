from __future__ import annotations

from collections.abc import Callable
from typing import Any

from analysis.climate import ClimateCriterion
from analysis.decision_model import DecisionModel
from analysis.distance_criterion import DistanceCriterion
from analysis.flood_hazard import FloodHazardCriterion
from analysis.grid_infrastructure import (
    GridInfrastructureCriterion,
)
from analysis.population_density import (
    PopulationDensityCriterion,
)
from analysis.protected_areas import ProtectedAreasCriterion
from analysis.telecom_infrastructure import (
    TelecomInfrastructureCriterion,
)
from analysis.water_bodies import WaterBodiesCriterion


class CandidateSiteEvaluator:
    """Run the operational AERIS criteria for one candidate point."""

    HARD_EXCLUSION_CRITERIA = (
        "hydro_hazard",
        "protected_areas",
        "water_bodies",
    )

    def __init__(
        self,
        roads_layer_url: str,
        transmission_layer_url: str,
        substation_layer_url: str,
        floodplain_layer_url: str,
        protected_lands_service_url: str,
        waterbodies_service_url: str,
    ) -> None:
        self.model = DecisionModel()

        self.climate = ClimateCriterion()

        self.grid = GridInfrastructureCriterion(
            transmission_layer_url=transmission_layer_url,
            substation_layer_url=substation_layer_url,
        )

        self.telecom = TelecomInfrastructureCriterion()

        self.protected_areas = ProtectedAreasCriterion(
            service_url=protected_lands_service_url,
        )

        self.water_bodies = WaterBodiesCriterion(
            service_url=waterbodies_service_url,
            search_radius_m=5000.0,
        )

        self.population_density = (
            PopulationDensityCriterion()
        )

        self.road_access = DistanceCriterion(
            criterion_name="road_access",
            source_layer=(
                "Maryland Road Centerlines - Comprehensive"
            ),
            layer_url=roads_layer_url,
            preferred_distance_key="road_m",
            search_delta_degrees=0.10,
            result_record_count=500,
        )

        self.hydro_hazard = FloodHazardCriterion(
            layer_url=floodplain_layer_url,
            buffer_m=91.0,
        )

    @staticmethod
    def _is_numeric_score(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
        )

    @staticmethod
    def _safe_evaluate(
        criterion_name: str,
        evaluation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            result = evaluation()

            if not isinstance(result, dict):
                raise RuntimeError(
                    "Criterion did not return a dictionary."
                )

            result = dict(result)
            result["status"] = "ok"

            return result

        except Exception as error:
            return {
                "criterion": criterion_name,
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
                "excluded": None,
                "normalized_score": None,
                "weighted_contribution": None,
            }

    def _criterion_weights(self) -> dict[str, float]:
        criteria = self.model.data.get("criteria", {})

        return {
            name: float(values["weight"])
            for name, values in criteria.items()
        }

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        results = {
            "climate": self._safe_evaluate(
                "climate",
                lambda: self.climate.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "grid_infrastructure": self._safe_evaluate(
                "grid_infrastructure",
                lambda: self.grid.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "telecom_infrastructure": self._safe_evaluate(
                "telecom_infrastructure",
                lambda: self.telecom.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "protected_areas": self._safe_evaluate(
                "protected_areas",
                lambda: self.protected_areas.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "water_bodies": self._safe_evaluate(
                "water_bodies",
                lambda: self.water_bodies.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "population_density": self._safe_evaluate(
                "population_density",
                lambda: self.population_density.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "road_access": self._safe_evaluate(
                "road_access",
                lambda: self.road_access.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
            "hydro_hazard": self._safe_evaluate(
                "hydro_hazard",
                lambda: self.hydro_hazard.evaluate(
                    lat=lat,
                    lon=lon,
                ),
            ),
        }

        weights = self._criterion_weights()
        configured_weight_total = sum(weights.values())

        partial_weighted_score = 0.0
        scored_weight = 0.0
        unscored_criteria: dict[str, dict[str, Any]] = {}

        for criterion_name, weight in weights.items():
            result = results.get(criterion_name)

            if result is None:
                unscored_criteria[criterion_name] = {
                    "weight": weight,
                    "reason": "criterion_not_executed",
                }
                continue

            if result.get("status") != "ok":
                unscored_criteria[criterion_name] = {
                    "weight": weight,
                    "reason": "source_or_processing_error",
                    "error": result.get("error"),
                }
                continue

            score = result.get("normalized_score")

            if not self._is_numeric_score(score):
                unscored_criteria[criterion_name] = {
                    "weight": weight,
                    "reason": result.get(
                        "scoring_status",
                        "methodology_not_yet_scored",
                    ),
                }
                continue

            score_value = max(
                0.0,
                min(1.0, float(score)),
            )

            scored_weight += weight
            partial_weighted_score += (
                score_value * weight
            )

        exclusion_checks_complete = True
        hard_exclusion_reasons: list[str] = []

        for criterion_name in (
            self.HARD_EXCLUSION_CRITERIA
        ):
            result = results.get(criterion_name, {})

            if result.get("status") != "ok":
                exclusion_checks_complete = False
                continue

            if result.get("excluded") is True:
                hard_exclusion_reasons.append(
                    criterion_name
                )

        hard_excluded = bool(hard_exclusion_reasons)

        unscored_weight = max(
            0.0,
            configured_weight_total - scored_weight,
        )

        if scored_weight > 0:
            provisional_normalized_score = (
                partial_weighted_score / scored_weight
            )
        else:
            provisional_normalized_score = None

        if configured_weight_total > 0:
            model_completion_percent = (
                scored_weight
                / configured_weight_total
                * 100
            )
        else:
            model_completion_percent = 0.0

        model_scoring_complete = (
            unscored_weight <= 0.000001
        )

        provisional_ranking_eligible = (
            not hard_excluded
            and exclusion_checks_complete
            and scored_weight > 0
        )

        final_ranking_eligible = (
            provisional_ranking_eligible
            and model_scoring_complete
        )

        if hard_excluded:
            decision_status = "excluded"
        elif not exclusion_checks_complete:
            decision_status = (
                "incomplete_exclusion_checks"
            )
        elif not model_scoring_complete:
            decision_status = "provisional"
        else:
            decision_status = "complete"

        effective_score = (
            0.0
            if hard_excluded
            else provisional_normalized_score
        )

        return {
            "analysis": (
                "AERIS Maryland data center "
                "candidate-site evaluation"
            ),
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "decision": {
                "status": decision_status,
                "hard_excluded": hard_excluded,
                "hard_exclusion_reasons": (
                    hard_exclusion_reasons
                ),
                "exclusion_checks_complete": (
                    exclusion_checks_complete
                ),
                "provisional_ranking_eligible": (
                    provisional_ranking_eligible
                ),
                "final_ranking_eligible": (
                    final_ranking_eligible
                ),
            },
            "score_summary": {
                "configured_weight_total": round(
                    configured_weight_total,
                    6,
                ),
                "scored_weight": round(
                    scored_weight,
                    6,
                ),
                "unscored_weight": round(
                    unscored_weight,
                    6,
                ),
                "model_completion_percent": round(
                    model_completion_percent,
                    2,
                ),
                "partial_weighted_score": round(
                    partial_weighted_score,
                    6,
                ),
                "provisional_normalized_score": (
                    round(
                        provisional_normalized_score,
                        6,
                    )
                    if provisional_normalized_score
                    is not None
                    else None
                ),
                "effective_score_after_exclusions": (
                    round(effective_score, 6)
                    if effective_score is not None
                    else None
                ),
            },
            "unscored_criteria": unscored_criteria,
            "criteria": results,
            "interpretation": {
                "partial_weighted_score": (
                    "Sum of weighted contributions from "
                    "criteria that currently have scores."
                ),
                "provisional_normalized_score": (
                    "Partial score divided by the scored "
                    "weight. This is useful for provisional "
                    "comparison but is not a finished model "
                    "score while criteria remain unscored."
                ),
                "effective_score_after_exclusions": (
                    "Set to zero when a hard exclusion is "
                    "triggered."
                ),
            },
        }
