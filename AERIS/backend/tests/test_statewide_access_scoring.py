from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.scoring import (
    inverse_distance_score_series,
    provider_diversity_score_series,
    telecom_proximity_score_series,
)


class StatewideAccessScoringTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.proximity_scores = {
            "direct_coverage": 1.00,
            "within_500_m": 0.90,
            "within_1000_m": 0.80,
            "within_2000_m": 0.65,
            "within_5000_m": 0.40,
            "beyond_5000_m": 0.10,
        }

        self.diversity_scores = {
            "zero_providers": 0.00,
            "one_provider": 0.30,
            "two_providers": 0.55,
            "three_providers": 0.75,
            "four_or_more_providers": 1.00,
        }

    def test_major_road_distance_curve(
        self,
    ) -> None:
        scores = (
            inverse_distance_score_series(
                pd.Series(
                    [
                        0,
                        800,
                        2900,
                        5000,
                        6000,
                    ]
                ),
                best_m=800,
                worst_m=5000,
            )
        )

        self.assertEqual(
            scores.tolist(),
            [
                1.0,
                1.0,
                0.5,
                0.0,
                0.0,
            ],
        )

    def test_telecom_proximity_bands(
        self,
    ) -> None:
        scores = (
            telecom_proximity_score_series(
                pd.Series(
                    [
                        0,
                        300,
                        750,
                        1500,
                        4000,
                        7000,
                        None,
                    ]
                ),
                self.proximity_scores,
            )
        )

        self.assertEqual(
            scores.tolist(),
            [
                1.0,
                0.9,
                0.8,
                0.65,
                0.4,
                0.1,
                0.1,
            ],
        )

    def test_provider_diversity_bands(
        self,
    ) -> None:
        scores = (
            provider_diversity_score_series(
                pd.Series(
                    [
                        0,
                        1,
                        2,
                        3,
                        4,
                        8,
                    ]
                ),
                self.diversity_scores,
            )
        )

        self.assertEqual(
            scores.tolist(),
            [
                0.0,
                0.3,
                0.55,
                0.75,
                1.0,
                1.0,
            ],
        )


if __name__ == "__main__":
    unittest.main()
