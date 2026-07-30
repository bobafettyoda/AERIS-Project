from __future__ import annotations

import unittest
from typing import Any

from analysis.candidate_site import CandidateSiteEvaluator
from app.config import (
    FEMA_FLOODPLAIN_URL,
    PROTECTED_LANDS_URL,
    ROADS_LAYER_URL,
    SUBSTATIONS_LAYER_URL,
    TRANSMISSION_LINES_LAYER_URL,
    WATERBODIES_URL,
)


class CandidateSiteEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = CandidateSiteEvaluator(
            roads_layer_url=ROADS_LAYER_URL,
            transmission_layer_url=(
                TRANSMISSION_LINES_LAYER_URL
            ),
            substation_layer_url=SUBSTATIONS_LAYER_URL,
            floodplain_layer_url=FEMA_FLOODPLAIN_URL,
            protected_lands_service_url=(
                PROTECTED_LANDS_URL
            ),
            waterbodies_service_url=WATERBODIES_URL,
        )

    @staticmethod
    def _result(
        criterion: str,
        score: float,
        excluded: bool = False,
    ) -> dict[str, Any]:
        return {
            "criterion": criterion,
            "normalized_score": score,
            "excluded": excluded,
        }

    def _stub_all(
        self,
        *,
        overrides: dict[str, dict[str, Any]]
        | None = None,
        failures: set[str] | None = None,
    ) -> None:
        overrides = overrides or {}
        failures = failures or set()

        criteria = {
            "climate": self.evaluator.climate,
            "grid_infrastructure": self.evaluator.grid,
            "telecom_infrastructure": (
                self.evaluator.telecom
            ),
            "protected_areas": (
                self.evaluator.protected_areas
            ),
            "water_bodies": self.evaluator.water_bodies,
            "population_density": (
                self.evaluator.population_density
            ),
            "road_access": self.evaluator.road_access,
            "hydro_hazard": (
                self.evaluator.hydro_hazard
            ),
        }

        for criterion_name, criterion_object in (
            criteria.items()
        ):
            if criterion_name in failures:
                def fail(
                    lat: float,
                    lon: float,
                    name: str = criterion_name,
                ) -> dict[str, Any]:
                    raise RuntimeError(
                        f"{name} source unavailable"
                    )

                criterion_object.evaluate = fail
                continue

            result = overrides.get(
                criterion_name,
                self._result(
                    criterion=criterion_name,
                    score=1.0,
                    excluded=False,
                ),
            )

            criterion_object.evaluate = (
                lambda lat, lon, value=result: dict(value)
            )

    def test_complete_site_receives_final_score(
        self,
    ) -> None:
        self._stub_all()

        result = self.evaluator.evaluate(
            lat=38.9897,
            lon=-76.9378,
        )

        self.assertEqual(
            result["decision"]["status"],
            "complete",
        )
        self.assertFalse(
            result["decision"]["hard_excluded"]
        )
        self.assertTrue(
            result["decision"][
                "final_ranking_eligible"
            ]
        )
        self.assertEqual(
            result["score_summary"][
                "model_completion_percent"
            ],
            100.0,
        )
        self.assertEqual(
            result["score_summary"][
                "final_suitability_score"
            ],
            1.0,
        )

    def test_water_intersection_hard_excludes_site(
        self,
    ) -> None:
        self._stub_all(
            overrides={
                "water_bodies": self._result(
                    criterion="water_bodies",
                    score=0.0,
                    excluded=True,
                )
            }
        )

        result = self.evaluator.evaluate(
            lat=38.9897,
            lon=-76.9378,
        )

        self.assertEqual(
            result["decision"]["status"],
            "excluded",
        )
        self.assertTrue(
            result["decision"]["hard_excluded"]
        )
        self.assertIn(
            "water_bodies",
            result["decision"][
                "hard_exclusion_reasons"
            ],
        )
        self.assertEqual(
            result["score_summary"][
                "effective_score_after_exclusions"
            ],
            0.0,
        )
        self.assertEqual(
            result["score_summary"][
                "final_suitability_score"
            ],
            0.0,
        )

    def test_failed_scored_criterion_is_not_final(
        self,
    ) -> None:
        self._stub_all(
            failures={"climate"},
        )

        result = self.evaluator.evaluate(
            lat=38.9897,
            lon=-76.9378,
        )

        self.assertEqual(
            result["decision"]["status"],
            "provisional",
        )
        self.assertFalse(
            result["decision"][
                "final_ranking_eligible"
            ]
        )
        self.assertIsNone(
            result["score_summary"][
                "final_suitability_score"
            ]
        )
        self.assertIn(
            "climate",
            result["unscored_criteria"],
        )


if __name__ == "__main__":
    unittest.main()
