from __future__ import annotations

import unittest

import pandas as pd

from analysis.statewide.scenario import (
    ScenarioEngine,
    TECHNICAL_CRITERIA,
    normalize_weights,
)


class StatewideScenarioTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.engine = ScenarioEngine()

        self.equal_weights = {
            criterion: 1.0
            for criterion
            in TECHNICAL_CRITERIA
        }

    @staticmethod
    def _row(
        cell_id: str,
        score: float,
        x_m: float,
        y_m: float,
        equity_gate: str = "PASS",
        hard_excluded: bool = False,
    ) -> dict:
        row = {
            "cell_id": cell_id,
            "analysis_x_m": x_m,
            "analysis_y_m": y_m,
            "equity_gate": equity_gate,
            "hard_excluded": (
                hard_excluded
            ),
        }

        for criterion in (
            TECHNICAL_CRITERIA
        ):
            row[criterion] = score

        return row

    def test_weights_are_normalized(
        self,
    ) -> None:
        normalized = normalize_weights(
            {
                "climate": 25,
                "grid_infrastructure": 75,
            }
        )

        self.assertAlmostEqual(
            normalized["climate"],
            0.25,
        )

        self.assertAlmostEqual(
            normalized[
                "grid_infrastructure"
            ],
            0.75,
        )

        self.assertAlmostEqual(
            sum(normalized.values()),
            1.0,
        )

    def test_high_burden_never_becomes_auto_recommendation(
        self,
    ) -> None:
        cells = pd.DataFrame(
            [
                self._row(
                    cell_id="PASS-LOWER",
                    score=0.82,
                    x_m=0,
                    y_m=0,
                    equity_gate="PASS",
                ),
                self._row(
                    cell_id="HIGH-BURDEN-HIGHER",
                    score=0.99,
                    x_m=20000,
                    y_m=0,
                    equity_gate=(
                        "HIGH_BURDEN"
                    ),
                ),
            ]
        )

        scored = self.engine.score_cells(
            cells,
            self.equal_weights,
        )

        high_burden = scored.loc[
            scored["cell_id"]
            == "HIGH-BURDEN-HIGHER"
        ].iloc[0]

        self.assertAlmostEqual(
            high_burden[
                "technical_score"
            ],
            0.99,
        )

        self.assertFalse(
            bool(
                high_burden[
                    "auto_recommendation_eligible"
                ]
            )
        )

        top = self.engine.select_top_n(
            scored,
            count=1,
            minimum_spacing_m=0,
            mode="auto",
        )

        self.assertEqual(
            top.iloc[0]["cell_id"],
            "PASS-LOWER",
        )

    def test_score_band_supports_diamond_in_the_rough_search(
        self,
    ) -> None:
        cells = pd.DataFrame(
            [
                self._row(
                    "LOW",
                    0.65,
                    0,
                    0,
                ),
                self._row(
                    "DIAMOND",
                    0.76,
                    10000,
                    0,
                    equity_gate="CAUTION",
                ),
                self._row(
                    "STRONG",
                    0.86,
                    20000,
                    0,
                ),
                self._row(
                    "PREMIUM",
                    0.94,
                    30000,
                    0,
                ),
            ]
        )

        scored = self.engine.score_cells(
            cells,
            self.equal_weights,
        )

        band = (
            self.engine.filter_score_band(
                scored,
                minimum=0.70,
                maximum=0.90,
                mode="exploration",
            )
        )

        self.assertEqual(
            band["cell_id"].tolist(),
            ["STRONG", "DIAMOND"],
        )

    def test_top_candidates_respect_spacing(
        self,
    ) -> None:
        cells = pd.DataFrame(
            [
                self._row(
                    "A",
                    0.95,
                    0,
                    0,
                ),
                self._row(
                    "B-TOO-CLOSE",
                    0.94,
                    5000,
                    0,
                ),
                self._row(
                    "C",
                    0.90,
                    16000,
                    0,
                ),
                self._row(
                    "D",
                    0.87,
                    32000,
                    0,
                ),
            ]
        )

        scored = self.engine.score_cells(
            cells,
            self.equal_weights,
        )

        selected = (
            self.engine.select_top_n(
                scored,
                count=3,
                minimum_spacing_m=10000,
                mode="auto",
            )
        )

        self.assertEqual(
            selected["cell_id"].tolist(),
            ["A", "C", "D"],
        )


if __name__ == "__main__":
    unittest.main()
