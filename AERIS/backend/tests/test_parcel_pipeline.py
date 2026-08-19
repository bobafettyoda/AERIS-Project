from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import box

from analysis.parcels.pipeline import (
    normalize_parcels,
    scope_from_bbox,
)


class ParcelPipelineTests(
    unittest.TestCase
):
    def test_bbox_scope_is_deterministic(
        self,
    ) -> None:
        first = scope_from_bbox(
            west=-76.96,
            south=38.98,
            east=-76.92,
            north=39.01,
            scope_name="College Park",
        )

        second = scope_from_bbox(
            west=-76.96,
            south=38.98,
            east=-76.92,
            north=39.01,
            scope_name="College Park",
        )

        self.assertEqual(
            first.scope_id,
            second.scope_id,
        )

    def test_normalization_never_confirms_availability(
        self,
    ) -> None:
        source = gpd.GeoDataFrame(
            {
                "_source_object_id": [
                    1,
                    2,
                    3,
                ],
                "JURSCODE": [
                    "16",
                    "16",
                    "16",
                ],
                "ACCTID": [
                    "A",
                    "B",
                    "C",
                ],
                "ADDRESS": [
                    "1 University Ave",
                    "2 Industrial Way",
                    "3 Unknown Road",
                ],
                "ZONING": [
                    "INST",
                    "IE",
                    "",
                ],
                "DESCLU": [
                    "University",
                    "Industrial",
                    "",
                ],
                "DESCEXCL": [
                    "Public",
                    "",
                    "",
                ],
                "YEARBLT": [
                    1990,
                    2000,
                    None,
                ],
                "SQFTSTRC": [
                    50000,
                    10000,
                    None,
                ],
                "NFMIMPVL": [
                    5000000,
                    1000000,
                    None,
                ],
                "POLYACRES": [
                    5,
                    8,
                    4,
                ],
            },
            geometry=[
                box(
                    0,
                    0,
                    100,
                    100,
                ),
                box(
                    200,
                    0,
                    300,
                    100,
                ),
                box(
                    400,
                    0,
                    500,
                    100,
                ),
            ],
            crs="EPSG:26985",
        )

        config = {
            "normalization": {
                "minimum_geometry_area_sq_m": (
                    1
                ),
                "minimum_parcel_acres": (
                    0.01
                ),
                "acreage_conversion": {
                    "square_meters_per_acre": (
                        4046.8564224
                    ),
                },
            },
            "classification": {
                "public_exemption_keywords": [
                    "public",
                    "government",
                ],
                "institutional_keywords": [
                    "university",
                    "school",
                ],
            },
        }

        scope = scope_from_bbox(
            west=-77,
            south=38,
            east=-76,
            north=39,
            scope_name="Test",
        )

        result = normalize_parcels(
            source_frame=source,
            config=config,
            scope=scope,
        )

        self.assertFalse(
            result[
                "availability_confirmed"
            ].any()
        )

        self.assertEqual(
            result.iloc[0][
                "availability_status"
            ],
            "PUBLIC_OR_INSTITUTIONAL",
        )

        self.assertEqual(
            result.iloc[1][
                "availability_status"
            ],
            (
                "EXISTING_USE_REVIEW_"
                "REQUIRED"
            ),
        )

        self.assertEqual(
            result.iloc[2][
                "availability_status"
            ],
            "POTENTIAL_FURTHER_REVIEW",
        )


if __name__ == "__main__":
    unittest.main()
