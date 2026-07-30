from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.foundation_join import (
    equity_gate_status,
    normalize_percentage,
    parse_boolean_flag,
    population_density_score,
)


class FoundationJoinTests(
    unittest.TestCase
):
    def test_boolean_flags(
        self,
    ) -> None:
        self.assertIs(
            parse_boolean_flag("Yes"),
            True,
        )

        self.assertIs(
            parse_boolean_flag("0"),
            False,
        )

        self.assertIsNone(
            parse_boolean_flag(None)
        )

    def test_equity_gate_precedence(
        self,
    ) -> None:
        self.assertEqual(
            equity_gate_status(
                enviroscreen_available=False,
                overburdened=None,
                underserved=None,
            ),
            "INSUFFICIENT_DATA",
        )

        self.assertEqual(
            equity_gate_status(
                enviroscreen_available=True,
                overburdened=True,
                underserved=True,
            ),
            "HIGH_BURDEN",
        )

        self.assertEqual(
            equity_gate_status(
                enviroscreen_available=True,
                overburdened=False,
                underserved=True,
            ),
            "CAUTION",
        )

        self.assertEqual(
            equity_gate_status(
                enviroscreen_available=True,
                overburdened=False,
                underserved=False,
            ),
            "PASS",
        )

    def test_percentages_support_zero_to_one_and_zero_to_one_hundred(
        self,
    ) -> None:
        result = normalize_percentage(
            pd.Series(
                [
                    0.81,
                    87,
                    -999,
                ]
            )
        )

        self.assertAlmostEqual(
            result.iloc[0],
            81.0,
        )

        self.assertAlmostEqual(
            result.iloc[1],
            87.0,
        )

        self.assertTrue(
            pd.isna(
                result.iloc[2]
            )
        )

    def test_population_score_matches_existing_calibration(
        self,
    ) -> None:
        result = population_density_score(
            pd.Series([2752.72]),
            base_score=0.70,
            density_multiplier=0.0001,
            minimum_score=0.0,
            maximum_score=1.0,
        )

        self.assertAlmostEqual(
            result.iloc[0],
            0.975272,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
