from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import box

from analysis.parcels.envelope_pipeline import (
    SQUARE_METERS_PER_ACRE,
    analyze_parcel_geometries,
)


class ParcelEnvelopeTests(
    unittest.TestCase
):
    def parcels(
        self,
        geometry,
    ) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(
            {
                "parcel_id": [
                    "TEST-PARCEL",
                ],
            },
            geometry=[
                geometry
            ],
            crs="EPSG:26985",
        )

    def test_overlapping_constraints_are_not_double_counted(
        self,
    ) -> None:
        parcel = box(
            0,
            0,
            100,
            100,
        )

        water = box(
            0,
            0,
            30,
            100,
        )

        protected = box(
            20,
            0,
            50,
            100,
        )

        (
            analysis,
            envelopes,
            largest,
        ) = analyze_parcel_geometries(
            parcels=self.parcels(
                parcel
            ),
            scope_geometry=parcel,
            constraints={
                "water": water,
                "protected_lands": (
                    protected
                ),
            },
            precision_m=0.01,
            minimum_component_area_acres=(
                0.001
            ),
        )

        expected_analysis = (
            10000
            / SQUARE_METERS_PER_ACRE
        )

        expected_constrained = (
            5000
            / SQUARE_METERS_PER_ACRE
        )

        expected_unconstrained = (
            5000
            / SQUARE_METERS_PER_ACRE
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "analysis_area_acres"
            ],
            expected_analysis,
            places=5,
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "mapped_constrained_area_acres"
            ],
            expected_constrained,
            places=5,
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "preliminary_unconstrained_area_acres"
            ],
            expected_unconstrained,
            places=5,
        )

        self.assertEqual(
            len(envelopes),
            1,
        )

        self.assertEqual(
            len(largest),
            1,
        )

    def test_constraint_can_split_envelope(
        self,
    ) -> None:
        parcel = box(
            0,
            0,
            100,
            100,
        )

        divider = box(
            45,
            0,
            55,
            100,
        )

        (
            analysis,
            _,
            _,
        ) = analyze_parcel_geometries(
            parcels=self.parcels(
                parcel
            ),
            scope_geometry=parcel,
            constraints={
                "water": divider,
            },
            precision_m=0.01,
            minimum_component_area_acres=(
                0.001
            ),
        )

        expected_largest = (
            4500
            / SQUARE_METERS_PER_ACRE
        )

        self.assertEqual(
            int(
                analysis.iloc[0][
                    "unconstrained_component_count"
                ]
            ),
            2,
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "largest_contiguous_unconstrained_acres"
            ],
            expected_largest,
            places=5,
        )

    def test_scope_limits_analysis_area(
        self,
    ) -> None:
        parcel = box(
            0,
            0,
            200,
            100,
        )

        scope = box(
            0,
            0,
            100,
            100,
        )

        (
            analysis,
            _,
            _,
        ) = analyze_parcel_geometries(
            parcels=self.parcels(
                parcel
            ),
            scope_geometry=scope,
            constraints={},
            precision_m=0.01,
            minimum_component_area_acres=(
                0.001
            ),
        )

        expected = (
            10000
            / SQUARE_METERS_PER_ACRE
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "analysis_area_acres"
            ],
            expected,
            places=5,
        )

        self.assertAlmostEqual(
            analysis.iloc[0][
                "preliminary_unconstrained_area_acres"
            ],
            expected,
            places=5,
        )


if __name__ == "__main__":
    unittest.main()
