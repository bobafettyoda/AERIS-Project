from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.climate_final_pipeline import (
    apply_climate_score,
    apply_final_technical_model,
    parse_power_regional_climatology,
)


def decision_model() -> dict:
    criteria = {
        "climate": {
            "weight": 0.25,
        },
        "grid_infrastructure": {
            "weight": 0.154,
        },
        "telecom_infrastructure": {
            "weight": 0.154,
        },
        "protected_areas": {
            "weight": 0.154,
        },
        "water_bodies": {
            "weight": 0.0847,
        },
        "population_density": {
            "weight": 0.0847,
        },
        "road_access": {
            "weight": 0.0795,
        },
        "hydro_hazard": {
            "weight": 0.039,
        },
    }

    return {
        "criteria": criteria,
        "climate_scoring": {
            "method": (
                "nasa_power_temperature_proxy"
            ),
            "annual_temperature_component_weight": (
                0.60
            ),
            "july_temperature_component_weight": (
                0.40
            ),
            "annual_mean_temperature_points": [
                {
                    "temperature_c": 8,
                    "score": 1.00,
                },
                {
                    "temperature_c": 12,
                    "score": 0.90,
                },
                {
                    "temperature_c": 16,
                    "score": 0.70,
                },
                {
                    "temperature_c": 20,
                    "score": 0.40,
                },
                {
                    "temperature_c": 24,
                    "score": 0.10,
                },
            ],
            "july_mean_temperature_points": [
                {
                    "temperature_c": 18,
                    "score": 1.00,
                },
                {
                    "temperature_c": 22,
                    "score": 0.85,
                },
                {
                    "temperature_c": 26,
                    "score": 0.65,
                },
                {
                    "temperature_c": 30,
                    "score": 0.35,
                },
                {
                    "temperature_c": 34,
                    "score": 0.10,
                },
            ],
        },
    }


class StatewideClimateFinalTests(
    unittest.TestCase
):
    def test_regional_response_parser(
        self,
    ) -> None:
        payload = {
            "type": "FeatureCollection",
            "header": {
                "fill_value": -999.0,
            },
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            -77.0,
                            39.0,
                            100.0,
                        ],
                    },
                    "properties": {
                        "parameter": {
                            "T2M": {
                                "JUL": 25.79,
                                "ANN": 13.15,
                            }
                        }
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            -76.5,
                            39.0,
                            80.0,
                        ],
                    },
                    "properties": {
                        "parameter": {
                            "T2M": {
                                "JUL": 26.0,
                                "ANN": 13.5,
                            }
                        }
                    },
                },
            ],
        }

        frame = (
            parse_power_regional_climatology(
                payload,
                parameter_name="T2M",
            )
        )

        self.assertEqual(
            len(frame),
            2,
        )

        self.assertAlmostEqual(
            frame.iloc[0][
                "annual_mean_temperature_c"
            ],
            13.15,
        )

    def test_known_point_climate_score(
        self,
    ) -> None:
        frame = pd.DataFrame(
            {
                "annual_mean_temperature_c": [
                    13.15
                ],
                "july_mean_temperature_c": [
                    25.79
                ],
            }
        )

        result = apply_climate_score(
            frame,
            decision_model(),
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "climate_annual_component_score"
            ],
            0.8425,
            places=6,
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "climate_july_component_score"
            ],
            0.6605,
            places=6,
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "climate_score"
            ],
            0.7697,
            places=6,
        )

    def test_complete_model_normalizes_weight_total(
        self,
    ) -> None:
        frame = pd.DataFrame(
            {
                "climate_score": [1.0],
                "grid_infrastructure_score": [
                    1.0
                ],
                "telecom_infrastructure_score": [
                    1.0
                ],
                "protected_areas_score": [
                    1.0
                ],
                "water_bodies_score": [
                    1.0
                ],
                "population_density_score": [
                    1.0
                ],
                "road_access_score": [
                    1.0
                ],
                "hydro_hazard_score": [
                    1.0
                ],
                "environmental_hard_excluded": [
                    False
                ],
                "regional_land_threshold_pass": [
                    True
                ],
                "equity_gate": [
                    "PASS"
                ],
            }
        )

        result = (
            apply_final_technical_model(
                frame,
                decision_model(),
            )
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "technical_weighted_sum"
            ],
            0.9999,
            places=6,
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "technical_suitability_score"
            ],
            1.0,
            places=6,
        )

        self.assertTrue(
            bool(
                result.iloc[0][
                    "auto_screen_eligible"
                ]
            )
        )

        self.assertFalse(
            bool(
                result.iloc[0][
                    "automated_recommendation_ready"
                ]
            )
        )

    def test_exclusion_sets_effective_score_zero(
        self,
    ) -> None:
        frame = pd.DataFrame(
            {
                "climate_score": [0.8],
                "grid_infrastructure_score": [
                    0.8
                ],
                "telecom_infrastructure_score": [
                    0.8
                ],
                "protected_areas_score": [
                    0.0
                ],
                "water_bodies_score": [
                    0.8
                ],
                "population_density_score": [
                    0.8
                ],
                "road_access_score": [
                    0.8
                ],
                "hydro_hazard_score": [
                    1.0
                ],
                "environmental_hard_excluded": [
                    True
                ],
                "regional_land_threshold_pass": [
                    True
                ],
                "equity_gate": [
                    "PASS"
                ],
            }
        )

        result = (
            apply_final_technical_model(
                frame,
                decision_model(),
            )
        )

        self.assertEqual(
            result.iloc[0][
                "effective_suitability_score"
            ],
            0.0,
        )

        self.assertEqual(
            result.iloc[0][
                "final_model_status"
            ],
            "EXCLUDED",
        )

        self.assertFalse(
            bool(
                result.iloc[0][
                    "auto_screen_eligible"
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
