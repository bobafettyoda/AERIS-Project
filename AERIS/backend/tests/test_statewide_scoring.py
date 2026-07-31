from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.scoring import (
    inverse_distance_score_series,
    piecewise_linear_series,
    weighted_composite_series,
)


class StatewideScoringTests(
    unittest.TestCase
):
    def test_inverse_distance_score(
        self,
    ) -> None:
        score = (
            inverse_distance_score_series(
                pd.Series(
                    [
                        0,
                        2000,
                        4000,
                        5000,
                    ]
                ),
                best_m=0,
                worst_m=4000,
            )
        )

        self.assertEqual(
            score.tolist(),
            [
                1.0,
                0.5,
                0.0,
                0.0,
            ],
        )

    def test_grid_composite(
        self,
    ) -> None:
        result = (
            weighted_composite_series(
                [
                    (
                        pd.Series(
                            [0.705725]
                        ),
                        0.60,
                    ),
                    (
                        pd.Series(
                            [0.414845]
                        ),
                        0.40,
                    ),
                ]
            )
        )

        self.assertAlmostEqual(
            result.iloc[0],
            0.589373,
            places=6,
        )

    def test_population_curve_declines_after_peak(
        self,
    ) -> None:
        result = piecewise_linear_series(
            pd.Series(
                [
                    3000,
                    6000,
                    12000,
                ]
            ),
            [
                (0, 0.30),
                (250, 0.30),
                (1000, 0.80),
                (3000, 1.00),
                (6000, 0.50),
                (12000, 0.20),
            ],
        )

        self.assertEqual(
            result.tolist(),
            [
                1.0,
                0.5,
                0.2,
            ],
        )


if __name__ == "__main__":
    unittest.main()
