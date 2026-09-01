from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import GeometryCollection, LineString, box

from analysis.site_feasibility.pipeline import road_metrics


class SiteFeasibilityRoadTests(unittest.TestCase):
    def test_frontage_proxy_and_nearest_road(self) -> None:
        parcels = gpd.GeoDataFrame(
            {
                "parcel_id": ["A", "B"],
            },
            geometry=[
                box(0, 0, 100, 100),
                box(500, 0, 600, 100),
            ],
            crs="EPSG:26985",
        )
        roads = gpd.GeoDataFrame(
            {
                "road_name": ["Frontage Road"],
                "road_class": ["LOCAL_OTHER"],
                "road_rank": [4],
            },
            geometry=[LineString([(0, -5), (100, -5)])],
            crs="EPSG:26985",
        )
        site_geometries = parcels.geometry.copy()
        result = road_metrics(
            parcels=parcels,
            site_geometries=site_geometries,
            roads=roads,
            frontage_tolerance_m=10,
            minimum_frontage_proxy_m=15,
            direct_frontage_excluded_classes=("INTERSTATE",),
            near_road_threshold_m=100,
            remote_road_threshold_m=500,
        )
        self.assertEqual(
            result.iloc[0]["road_access_status"],
            "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        )
        self.assertGreater(result.iloc[0]["road_frontage_proxy_m"], 90)
        self.assertEqual(result.iloc[1]["road_access_status"], "DISTANT_MAPPED_PUBLIC_ROAD")
        self.assertFalse(result["road_access_confirmed"].any())

    def test_geometry_collection_parcel_uses_polygonal_boundary(self) -> None:
        parcel_polygon = box(
            0,
            0,
            100,
            100,
        )

        parcels = gpd.GeoDataFrame(
            {
                "parcel_id": ["A"],
            },
            geometry=[
                GeometryCollection(
                    [
                        parcel_polygon,
                        LineString(
                            [
                                (150, 0),
                                (150, 100),
                            ]
                        ),
                    ]
                ),
            ],
            crs="EPSG:26985",
        )

        roads = gpd.GeoDataFrame(
            {
                "road_name": [
                    "Frontage Road",
                ],
                "road_class": [
                    "LOCAL_OTHER",
                ],
                "road_rank": [
                    4,
                ],
            },
            geometry=[
                LineString(
                    [
                        (0, -5),
                        (100, -5),
                    ]
                ),
            ],
            crs="EPSG:26985",
        )

        result = road_metrics(
            parcels=parcels,
            site_geometries=gpd.GeoSeries(
                [
                    parcel_polygon,
                ],
                crs=parcels.crs,
            ),
            roads=roads,
            frontage_tolerance_m=10,
            minimum_frontage_proxy_m=15,
            direct_frontage_excluded_classes=(
                "INTERSTATE",
            ),
            near_road_threshold_m=100,
            remote_road_threshold_m=500,
        )

        self.assertEqual(
            result.iloc[0][
                "road_access_status"
            ],
            "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        )

        self.assertGreater(
            result.iloc[0][
                "road_frontage_proxy_m"
            ],
            90,
        )

    def test_interstate_adjacency_is_not_direct_access(self) -> None:
        parcels = gpd.GeoDataFrame(
            {"parcel_id": ["A"]},
            geometry=[box(0, 0, 100, 100)],
            crs="EPSG:26985",
        )
        roads = gpd.GeoDataFrame(
            {
                "road_name": ["Interstate 95"],
                "road_class": ["INTERSTATE"],
                "road_rank": [1],
            },
            geometry=[LineString([(0, -5), (100, -5)])],
            crs="EPSG:26985",
        )
        result = road_metrics(
            parcels=parcels,
            site_geometries=parcels.geometry.copy(),
            roads=roads,
            frontage_tolerance_m=10,
            minimum_frontage_proxy_m=15,
            direct_frontage_excluded_classes=("INTERSTATE",),
            near_road_threshold_m=100,
            remote_road_threshold_m=500,
        )
        self.assertEqual(
            result.iloc[0]["road_access_status"],
            "LIMITED_ACCESS_ROAD_ADJACENCY_REVIEW_REQUIRED",
        )
        self.assertEqual(result.iloc[0]["road_frontage_proxy_m"], 0)
        self.assertGreater(
            result.iloc[0]["limited_access_adjacency_proxy_m"],
            90,
        )

    def test_frontage_proxy_is_clipped_to_analysis_scope(
        self,
    ) -> None:
        parcels = gpd.GeoDataFrame(
            {
                "parcel_id": [
                    "LONG",
                ],
            },
            geometry=[
                box(
                    0,
                    0,
                    1000,
                    100,
                ),
            ],
            crs="EPSG:26985",
        )

        roads = gpd.GeoDataFrame(
            {
                "road_name": [
                    "Long Road",
                ],
                "road_class": [
                    "LOCAL_OTHER",
                ],
                "road_rank": [
                    4,
                ],
            },
            geometry=[
                LineString(
                    [
                        (0, -5),
                        (1000, -5),
                    ]
                ),
            ],
            crs="EPSG:26985",
        )

        result = road_metrics(
            parcels=parcels,
            site_geometries=(
                parcels.geometry.copy()
            ),
            roads=roads,
            frontage_tolerance_m=10,
            minimum_frontage_proxy_m=15,
            direct_frontage_excluded_classes=(
                "INTERSTATE",
            ),
            near_road_threshold_m=100,
            remote_road_threshold_m=500,
            frontage_clip_geometry=box(
                0,
                0,
                100,
                100,
            ),
        )

        frontage = float(
            result.iloc[0][
                "road_frontage_proxy_m"
            ]
        )

        self.assertGreater(
            frontage,
            90,
        )

        self.assertLess(
            frontage,
            150,
        )


if __name__ == "__main__":
    unittest.main()
