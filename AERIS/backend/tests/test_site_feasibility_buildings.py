from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import box

from analysis.site_feasibility.pipeline import (
    building_metrics,
    safe_bool,
)


class SiteFeasibilityBuildingTests(
    unittest.TestCase
):
    def test_safe_bool_treats_missing_as_false(
        self,
    ) -> None:
        self.assertFalse(safe_bool(None))
        self.assertFalse(safe_bool(float("nan")))
        self.assertFalse(safe_bool("false"))
        self.assertTrue(safe_bool("true"))

    def parcels(self) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(
            {
                "parcel_id": ["P1"],
                "geometry_area_acres": [
                    10000 / 4046.8564224,
                ],
            },
            geometry=[box(0, 0, 100, 100)],
            crs="EPSG:26985",
        )

    def test_empty_available_source_means_zero_intersection(
        self,
    ) -> None:
        buildings = gpd.GeoDataFrame(
            {"geometry": []},
            geometry="geometry",
            crs="EPSG:26985",
        )

        result = building_metrics(
            parcels=self.parcels(),
            buildings=buildings,
            square_meters_per_acre=4046.8564224,
            source_available=True,
        )

        self.assertEqual(
            result.iloc[0][
                "building_reference_status"
            ],
            "REFERENCE_SOURCE_AVAILABLE_NO_INTERSECTION",
        )
        self.assertEqual(
            result.iloc[0][
                "building_reference_overlap_acres"
            ],
            0.0,
        )

    def test_failed_source_remains_unavailable(
        self,
    ) -> None:
        buildings = gpd.GeoDataFrame(
            {"geometry": []},
            geometry="geometry",
            crs="EPSG:26985",
        )

        result = building_metrics(
            parcels=self.parcels(),
            buildings=buildings,
            square_meters_per_acre=4046.8564224,
            source_available=False,
        )

        self.assertEqual(
            result.iloc[0][
                "building_reference_status"
            ],
            "UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
