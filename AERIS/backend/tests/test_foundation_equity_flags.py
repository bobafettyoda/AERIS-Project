from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import Point

from analysis.statewide.foundation_join import (
    equity_gate_status,
    standardize_enviroscreen,
)


class FoundationEquityFlagTests(
    unittest.TestCase
):
    def make_geometry(
        self,
        count: int,
    ) -> list[Point]:
        return [
            Point(
                -76.5 - index * 0.01,
                39.0,
            )
            for index in range(count)
        ]

    def test_documented_threshold_fallback(
        self,
    ) -> None:
        frame = gpd.GeoDataFrame(
            {
                "GEOID20": [
                    "24001000100",
                    "24001000200",
                    "24001000300",
                ],
                "OVERBURDENED_SUM": [
                    4,
                    2,
                    0,
                ],
                "MINORPCT": [
                    20.0,
                    60.0,
                    20.0,
                ],
                "LWINCPCT": [
                    10.0,
                    10.0,
                    10.0,
                ],
                "LINGISOPCT": [
                    5.0,
                    5.0,
                    5.0,
                ],
                "P_EJ": [
                    90.0,
                    70.0,
                    20.0,
                ],
            },
            geometry=self.make_geometry(3),
            crs="EPSG:4326",
        )

        standardized = (
            standardize_enviroscreen(
                frame
            )
        )

        self.assertEqual(
            standardized[
                "overburdened"
            ].tolist(),
            [
                True,
                False,
                False,
            ],
        )

        self.assertEqual(
            standardized[
                "underserved"
            ].tolist(),
            [
                False,
                True,
                False,
            ],
        )

        gates = [
            equity_gate_status(
                enviroscreen_available=True,
                overburdened=overburdened,
                underserved=underserved,
            )
            for (
                overburdened,
                underserved,
            )
            in zip(
                standardized[
                    "overburdened"
                ],
                standardized[
                    "underserved"
                ],
                strict=True,
            )
        ]

        self.assertEqual(
            gates,
            [
                "HIGH_BURDEN",
                "CAUTION",
                "PASS",
            ],
        )

    def test_official_flags_take_priority(
        self,
    ) -> None:
        frame = gpd.GeoDataFrame(
            {
                "GEOID20": [
                    "24001000100",
                ],
                "OVERBURDENED_COMMUNITY": [
                    0,
                ],
                "UNDERSERVED_COMMUNITY": [
                    0,
                ],
                # Derived fields deliberately
                # imply both classifications.
                "OVERBURDENED_SUM": [
                    8,
                ],
                "MINORPCT": [
                    90.0,
                ],
                "LWINCPCT": [
                    80.0,
                ],
                "LINGISOPCT": [
                    30.0,
                ],
            },
            geometry=self.make_geometry(1),
            crs="EPSG:4326",
        )

        standardized = (
            standardize_enviroscreen(
                frame
            )
        )

        self.assertFalse(
            bool(
                standardized.loc[
                    0,
                    "overburdened",
                ]
            )
        )

        self.assertFalse(
            bool(
                standardized.loc[
                    0,
                    "underserved",
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
