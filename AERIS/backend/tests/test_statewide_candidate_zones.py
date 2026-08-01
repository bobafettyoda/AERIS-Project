from __future__ import annotations

import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from analysis.statewide.candidate_zones_pipeline import (
    connected_component_labels,
    indicator_audit,
    score_with_weights,
    select_spaced_zones,
)


class CandidateZoneTests(
    unittest.TestCase
):
    def test_rook_adjacency_does_not_merge_diagonal_cells(
        self,
    ) -> None:
        frame = pd.DataFrame(
            {
                "row": [
                    0,
                    0,
                    1,
                    2,
                ],
                "column": [
                    0,
                    1,
                    1,
                    2,
                ],
            },
            index=[
                10,
                11,
                12,
                13,
            ],
        )

        labels = (
            connected_component_labels(
                frame
            )
        )

        self.assertEqual(
            labels.loc[10],
            labels.loc[11],
        )

        self.assertEqual(
            labels.loc[11],
            labels.loc[12],
        )

        self.assertNotEqual(
            labels.loc[12],
            labels.loc[13],
        )

    def test_top_zones_respect_spacing(
        self,
    ) -> None:
        zones = gpd.GeoDataFrame(
            {
                "zone_id": [
                    "A",
                    "B",
                    "C",
                ],
                "zone_rank_score": [
                    0.95,
                    0.94,
                    0.90,
                ],
                "anchor_x_m": [
                    0.0,
                    5000.0,
                    20000.0,
                ],
                "anchor_y_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
            },
            geometry=[
                box(0, 0, 1, 1),
                box(2, 0, 3, 1),
                box(4, 0, 5, 1),
            ],
            crs="EPSG:26985",
        )

        selected = select_spaced_zones(
            zones,
            top_n=2,
            minimum_spacing_m=10000,
        )

        self.assertEqual(
            selected[
                "zone_id"
            ].tolist(),
            [
                "A",
                "C",
            ],
        )

    def test_scenario_score_does_not_use_demographics(
        self,
    ) -> None:
        frame = pd.DataFrame(
            {
                "climate_score": [
                    0.8,
                    0.8,
                ],
                "grid_infrastructure_score": [
                    0.7,
                    0.7,
                ],
                "telecom_infrastructure_score": [
                    0.9,
                    0.9,
                ],
                "protected_areas_score": [
                    1.0,
                    1.0,
                ],
                "water_bodies_score": [
                    0.6,
                    0.6,
                ],
                "population_density_score": [
                    0.75,
                    0.75,
                ],
                "road_access_score": [
                    0.85,
                    0.85,
                ],
                "hydro_hazard_score": [
                    1.0,
                    1.0,
                ],
                "minority_or_hispanic_pct": [
                    10.0,
                    90.0,
                ],
                "low_income_pct": [
                    5.0,
                    80.0,
                ],
            }
        )

        weights = {
            "climate": 0.25,
            "grid_infrastructure": 0.154,
            "telecom_infrastructure": 0.154,
            "protected_areas": 0.154,
            "water_bodies": 0.0847,
            "population_density": 0.0847,
            "road_access": 0.0795,
            "hydro_hazard": 0.039,
        }

        score = score_with_weights(
            frame,
            weights,
        )

        self.assertAlmostEqual(
            score.iloc[0],
            score.iloc[1],
            places=8,
        )

    def test_disparity_audit_flags_overrepresentation(
        self,
    ) -> None:
        reference = pd.DataFrame(
            {
                "indicator": [
                    10.0,
                    10.0,
                    10.0,
                    90.0,
                ],
                "clipped_area_sq_km": [
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ],
            }
        )

        selected = pd.DataFrame(
            {
                "indicator": [
                    90.0,
                    90.0,
                    90.0,
                    90.0,
                ],
                "clipped_area_sq_km": [
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ],
            }
        )

        result = indicator_audit(
            reference,
            selected,
            column="indicator",
            label="Test indicator",
            threshold=75,
            disparity_config={
                "representation_ratio": 1.25,
                "percentage_point_difference": 5.0,
                "standardized_mean_difference": 0.25,
            },
            minimum_selected_cells=4,
        )

        self.assertTrue(
            result["flagged"]
        )

        self.assertGreater(
            result[
                "representation_ratio"
            ],
            1.25,
        )


if __name__ == "__main__":
    unittest.main()
