from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.environmental_constraints_pipeline import (
    binary_suitability_score,
    distance_intersection_flag,
    within_distance_flag,
)
from analysis.statewide.scoring import (
    piecewise_linear_series,
)


class EnvironmentalScoringTests(
    unittest.TestCase
):
    def test_water_curve_matches_known_point(
        self,
    ) -> None:
        result = piecewise_linear_series(
            pd.Series(
                [
                    241.67,
                ]
            ),
            [
                (0, 0.25),
                (100, 0.25),
                (300, 0.65),
                (1000, 1.00),
                (3000, 0.90),
                (5000, 0.80),
            ],
        )

        self.assertAlmostEqual(
            result.iloc[0],
            0.53334,
            places=5,
        )

    def test_direct_intersection_tolerance(
        self,
    ) -> None:
        result = (
            distance_intersection_flag(
                pd.Series(
                    [
                        0,
                        0.005,
                        0.02,
                        None,
                    ]
                ),
                tolerance_m=0.01,
            )
        )

        self.assertEqual(
            result.tolist(),
            [
                True,
                True,
                False,
                False,
            ],
        )

    def test_flood_buffer_threshold(
        self,
    ) -> None:
        result = (
            within_distance_flag(
                pd.Series(
                    [
                        0,
                        90.99,
                        91,
                        91.01,
                        None,
                    ]
                ),
                threshold_m=91,
            )
        )

        self.assertEqual(
            result.tolist(),
            [
                True,
                True,
                True,
                False,
                False,
            ],
        )

    def test_binary_suitability(
        self,
    ) -> None:
        result = (
            binary_suitability_score(
                pd.Series(
                    [
                        False,
                        True,
                    ]
                )
            )
        )

        self.assertEqual(
            result.tolist(),
            [
                1.0,
                0.0,
            ],
        )


if __name__ == "__main__":
    unittest.main()
