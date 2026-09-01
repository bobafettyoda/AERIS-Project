from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import box

from analysis.site_feasibility.assemblages import (
    CandidateThresholds,
    build_assemblages,
    candidate_eligibility,
    classify_site,
    right_of_way_indicator,
    transparent_candidate_score,
)


THRESHOLDS = CandidateThresholds(
    strong_largest_acres=50,
    strong_maximum_steep_fraction=0.10,
    strong_maximum_wetland_fraction=0.02,
    strong_maximum_building_fraction=0.05,
    strong_road_access=("DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",),
    promising_largest_acres=25,
    promising_maximum_steep_fraction=0.25,
    promising_maximum_wetland_fraction=0.10,
    promising_road_access=(
        "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        "NEAR_MAPPED_PUBLIC_ROAD",
    ),
    limited_minimum_acres=5,
)


class SiteFeasibilityAssemblageTests(unittest.TestCase):
    def test_classification_rules(self) -> None:
        self.assertEqual(
            classify_site(
                largest_contiguous_acres=60,
                steep_fraction=0.05,
                wetland_fraction=0,
                building_fraction=0.02,
                road_access_status="DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                thresholds=THRESHOLDS,
            ),
            "STRONG_PRELIMINARY_SITE_FEASIBILITY",
        )
        self.assertEqual(
            classify_site(
                largest_contiguous_acres=3,
                steep_fraction=0,
                wetland_fraction=0,
                building_fraction=0,
                road_access_status="DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                thresholds=THRESHOLDS,
            ),
            "LIMITED_PHYSICAL_SITE_FEASIBILITY",
        )

    def test_score_is_transparent_and_bounded(self) -> None:
        strong = transparent_candidate_score(
            largest_contiguous_acres=100,
            steep_fraction=0,
            wetland_fraction=0,
            building_fraction=0,
            road_access_status="DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
        )
        weak = transparent_candidate_score(
            largest_contiguous_acres=5,
            steep_fraction=0.8,
            wetland_fraction=0.5,
            building_fraction=0.5,
            road_access_status="REMOTE_FROM_MAPPED_PUBLIC_ROAD",
        )
        self.assertEqual(strong, 1.0)
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(weak, 0)

    def test_candidate_eligibility_blocks_public_and_hard_excluded(self) -> None:
        eligible = candidate_eligibility(
            public_land_flag=False,
            institutional_use_flag=False,
            statewide_hard_excluded=False,
            site_feasibility_class="PROMISING_PRELIMINARY_SITE_FEASIBILITY",
        )
        self.assertTrue(eligible[0])

        public = candidate_eligibility(
            public_land_flag=True,
            institutional_use_flag=False,
            statewide_hard_excluded=False,
            site_feasibility_class="STRONG_PRELIMINARY_SITE_FEASIBILITY",
        )
        self.assertFalse(public[0])
        self.assertEqual(public[1], "INELIGIBLE_PUBLIC_OR_INSTITUTIONAL")

        excluded = candidate_eligibility(
            public_land_flag=False,
            institutional_use_flag=False,
            statewide_hard_excluded=True,
            site_feasibility_class="STRONG_PRELIMINARY_SITE_FEASIBILITY",
        )
        self.assertFalse(excluded[0])
        self.assertEqual(
            excluded[1],
            "INELIGIBLE_REGIONAL_HARD_EXCLUSION",
        )

        right_of_way = candidate_eligibility(
            public_land_flag=False,
            institutional_use_flag=False,
            statewide_hard_excluded=False,
            site_feasibility_class="STRONG_PRELIMINARY_SITE_FEASIBILITY",
            right_of_way_flag=True,
        )

        self.assertFalse(
            right_of_way[0]
        )

        self.assertEqual(
            right_of_way[1],
            "INELIGIBLE_RIGHT_OF_WAY",
        )

        self.assertTrue(
            right_of_way_indicator(
                account_id="ROW",
                parcel_id=(
                    "ANNE-ROW-OID-22076"
                ),
            )
        )

        self.assertFalse(
            right_of_way_indicator(
                account_id="12345",
                parcel_id="ANNE-12345",
            )
        )

    def test_adjacent_site_envelopes_form_assemblage(self) -> None:
        parcel_analysis = gpd.GeoDataFrame(
            {
                "parcel_id": ["A", "B", "C"],
                "final_site_area_acres": [20.0, 20.0, 20.0],
                "public_land_flag": [False, False, False],
                "institutional_use_flag": [False, False, False],
                "right_of_way_flag": [False, False, False],
                "steep_slope_fraction": [0.1, 0.1, 0.1],
                "mapped_wetland_fraction": [0.0, 0.0, 0.0],
                "building_reference_fraction": [0.0, 0.0, 0.0],
                "road_access_status": [
                    "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                    "NEAR_MAPPED_PUBLIC_ROAD",
                    "REMOTE_FROM_MAPPED_PUBLIC_ROAD",
                ],
            },
            geometry=[
                box(0, 0, 100, 100),
                box(101, 0, 201, 100),
                box(1000, 0, 1100, 100),
            ],
            crs="EPSG:26985",
        )
        site_envelopes = parcel_analysis[["parcel_id", "geometry"]].copy()
        result = build_assemblages(
            parcel_analysis=parcel_analysis,
            site_envelopes=site_envelopes,
            square_meters_per_acre=4046.8564224,
            adjacency_gap_m=2,
            minimum_parcel_site_acres=1,
            minimum_total_site_acres=1,
            minimum_parcel_count=2,
            maximum_parcel_count=10,
            maximum_candidates=10,
            thresholds=THRESHOLDS,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["parcel_count"], 2)
        self.assertEqual(set(result.iloc[0]["parcel_ids"].split(";")), {"A", "B"})

    def test_right_of_way_parcel_is_excluded_from_assemblage(
        self,
    ) -> None:
        parcel_analysis = gpd.GeoDataFrame(
            {
                "parcel_id": [
                    "A",
                    "ROW",
                    "B",
                ],
                "final_site_area_acres": [
                    20.0,
                    100.0,
                    20.0,
                ],
                "public_land_flag": [
                    False,
                    False,
                    False,
                ],
                "institutional_use_flag": [
                    False,
                    False,
                    False,
                ],
                "right_of_way_flag": [
                    False,
                    True,
                    False,
                ],
                "steep_slope_fraction": [
                    0.0,
                    0.0,
                    0.0,
                ],
                "mapped_wetland_fraction": [
                    0.0,
                    0.0,
                    0.0,
                ],
                "building_reference_fraction": [
                    0.0,
                    0.0,
                    0.0,
                ],
                "road_access_status": [
                    "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                    "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                    "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
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
                    101,
                    0,
                    201,
                    100,
                ),
                box(
                    202,
                    0,
                    302,
                    100,
                ),
            ],
            crs="EPSG:26985",
        )

        site_envelopes = (
            parcel_analysis[
                [
                    "parcel_id",
                    "geometry",
                ]
            ].copy()
        )

        result = build_assemblages(
            parcel_analysis=parcel_analysis,
            site_envelopes=site_envelopes,
            square_meters_per_acre=4046.8564224,
            adjacency_gap_m=2,
            minimum_parcel_site_acres=1,
            minimum_total_site_acres=1,
            minimum_parcel_count=2,
            maximum_parcel_count=10,
            maximum_candidates=10,
            thresholds=THRESHOLDS,
        )

        self.assertTrue(
            result.empty
        )


if __name__ == "__main__":
    unittest.main()
