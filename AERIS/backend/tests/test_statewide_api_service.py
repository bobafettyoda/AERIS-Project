from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import (
    Point,
    box,
)

from analysis.statewide.api_service import (
    StatewideDataService,
    StatewidePaths,
)


class StatewideApiServiceTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temporary.name
        )

        derived = (
            self.root
            / "data"
            / "derived"
        )

        manifests = (
            self.root
            / "data"
            / "manifests"
        )

        derived.mkdir(
            parents=True
        )

        manifests.mkdir(
            parents=True
        )

        final_grid = gpd.GeoDataFrame(
            {
                "cell_id": [
                    "A",
                    "B",
                    "C",
                ],
                "analysis_lat": [
                    39.0,
                    39.1,
                    39.2,
                ],
                "analysis_lon": [
                    -76.5,
                    -76.6,
                    -76.7,
                ],
                "GEOID": [
                    "24033000100",
                    "24033000200",
                    "24005000100",
                ],
                "county": [
                    "033",
                    "033",
                    "005",
                ],
                "land_fraction": [
                    1.0,
                    1.0,
                    1.0,
                ],
                "clipped_area_sq_km": [
                    1.0,
                    1.0,
                    1.0,
                ],
                "technical_suitability_score": [
                    0.85,
                    0.75,
                    0.65,
                ],
                "effective_suitability_score": [
                    0.85,
                    0.0,
                    0.65,
                ],
                "hard_excluded": [
                    False,
                    True,
                    False,
                ],
                "water_hard_excluded": [
                    False,
                    True,
                    False,
                ],
                "protected_hard_excluded": [
                    False,
                    False,
                    False,
                ],
                "hydro_hazard_hard_excluded": [
                    False,
                    False,
                    False,
                ],
                "final_model_status": [
                    "COMPLETE",
                    "EXCLUDED",
                    "COMPLETE",
                ],
                "auto_screen_eligible": [
                    True,
                    False,
                    False,
                ],
                "exploration_screen_eligible": [
                    True,
                    False,
                    True,
                ],
                "automated_recommendation_ready": [
                    False,
                    False,
                    False,
                ],
                "equity_gate": [
                    "PASS",
                    "HIGH_BURDEN",
                    "CAUTION",
                ],
                "climate_score": [
                    0.8,
                    0.8,
                    0.8,
                ],
                "grid_infrastructure_score": [
                    0.8,
                    0.8,
                    0.8,
                ],
                "telecom_infrastructure_score": [
                    0.8,
                    0.8,
                    0.8,
                ],
                "protected_areas_score": [
                    1.0,
                    1.0,
                    1.0,
                ],
                "water_bodies_score": [
                    0.8,
                    0.0,
                    0.8,
                ],
                "population_density_score": [
                    0.8,
                    0.8,
                    0.8,
                ],
                "road_access_score": [
                    0.8,
                    0.8,
                    0.8,
                ],
                "hydro_hazard_score": [
                    1.0,
                    1.0,
                    1.0,
                ],
            },
            geometry=[
                box(0, 0, 1, 1),
                box(1, 0, 2, 1),
                box(2, 0, 3, 1),
            ],
            crs="EPSG:26985",
        )

        final_grid.to_file(
            derived
            / "maryland_grid_1km_final.gpkg",
            layer="cells",
            driver="GPKG",
            index=False,
        )

        preview = gpd.GeoDataFrame(
            final_grid.drop(
                columns="geometry"
            ),
            geometry=[
                Point(-76.5, 39.0),
                Point(-76.6, 39.1),
                Point(-76.7, 39.2),
            ],
            crs="EPSG:4326",
        )

        preview.to_file(
            derived
            / "maryland_grid_1km_final_points.geojson",
            driver="GeoJSON",
            index=False,
        )

        zones = gpd.GeoDataFrame(
            {
                "zone_id": [
                    "AUTO-Z001",
                ],
                "mean_score": [
                    0.85,
                ],
                "maximum_score": [
                    0.90,
                ],
                "area_sq_km": [
                    2.0,
                ],
                "cell_count": [
                    1,
                ],
                "dominant_county": [
                    "Prince George's County",
                ],
                "counties": [
                    "Prince George's County",
                ],
                "selection_rank": [
                    1,
                ],
            },
            geometry=[
                box(
                    -76.55,
                    38.95,
                    -76.45,
                    39.05,
                )
            ],
            crs="EPSG:4326",
        )

        zones.to_file(
            derived
            / "maryland_candidate_zones_top5.geojson",
            driver="GeoJSON",
            index=False,
        )

        zones.to_crs(
            "EPSG:26985"
        ).to_file(
            derived
            / "maryland_candidate_zones_auto.gpkg",
            layer="candidate_zones",
            driver="GPKG",
            index=False,
        )

        zones.to_crs(
            "EPSG:26985"
        ).to_file(
            derived
            / "maryland_candidate_zones_exploration.gpkg",
            layer="candidate_zones",
            driver="GPKG",
            index=False,
        )

        pd.DataFrame(
            {
                "mode": [
                    "auto",
                ],
                "zone_id": [
                    "AUTO-Z001",
                ],
                "cell_id": [
                    "A",
                ],
            }
        ).to_csv(
            derived
            / "maryland_candidate_zone_membership.csv",
            index=False,
        )

        final_manifest = {
            "snapshot_label": (
                "test"
            ),
            "final_model": {
                "cell_count": 3,
                "complete_cells": 3,
                "insufficient_data_cells": 0,
                "hard_excluded_cells": 1,
                "auto_screen_eligible_cells": 1,
                "exploration_screen_eligible_cells": 2,
                "technical_score_statistics": {
                    "count": 3,
                    "minimum": 0.65,
                    "maximum": 0.85,
                },
                "effective_score_statistics": {
                    "count": 3,
                    "minimum": 0.0,
                    "maximum": 0.85,
                },
            },
        }

        candidate_manifest = {
            "counts": {
                "auto_zone_count": 1,
                "top_zone_count": 1,
            },
            "terminology": {
                "allowed": (
                    "Regional screening "
                    "candidate zone"
                ),
            },
            "required_next_stage": [
                "Parcel review",
            ],
        }

        audit = {
            "audit_status": "PASS",
            "release_status": (
                "REGIONAL_SCREENING_"
                "SHORTLIST_READY"
            ),
            "screening_shortlist_ready": (
                True
            ),
            "automated_recommendation_ready": (
                False
            ),
            "material_flags": {},
        }

        score_bands = {
            "score_bands": [
                {
                    "id": "strong",
                    "label": "Strong",
                    "minimum": 0.8,
                    "maximum": 0.9,
                }
            ]
        }

        for path, payload in (
            (
                manifests
                / "statewide_climate_final.json",
                final_manifest,
            ),
            (
                manifests
                / "statewide_candidate_zones.json",
                candidate_manifest,
            ),
            (
                manifests
                / "statewide_bias_audit.json",
                audit,
            ),
            (
                manifests
                / "statewide_score_band_summary.json",
                score_bands,
            ),
        ):
            path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

        self.service = (
            StatewideDataService(
                StatewidePaths.from_root(
                    self.root
                )
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_grid_filters_by_exploration(
        self,
    ) -> None:
        result = (
            self.service
            .grid_feature_collection(
                minimum_score=0.70,
                eligibility=(
                    "exploration"
                ),
            )
        )

        ids = {
            feature[
                "properties"
            ]["cell_id"]
            for feature in result[
                "features"
            ]
        }

        self.assertEqual(
            ids,
            {
                "A",
            },
        )

    def test_cell_detail_reports_exclusion(
        self,
    ) -> None:
        result = (
            self.service.cell_detail(
                "B"
            )
        )

        self.assertTrue(
            result[
                "decision"
            ]["hard_excluded"]
        )

        self.assertIn(
            (
                "Mapped surface-water "
                "intersection"
            ),
            result[
                "decision"
            ][
                "exclusion_reasons"
            ],
        )

    def test_zone_detail_returns_members(
        self,
    ) -> None:
        result = (
            self.service.zone_detail(
                "AUTO-Z001"
            )
        )

        self.assertEqual(
            result[
                "membership"
            ]["member_count"],
            1,
        )

        self.assertEqual(
            result[
                "membership"
            ]["member_cell_ids"],
            [
                "A",
            ],
        )

    def test_file_cache_invalidates_when_source_changes(
        self,
    ) -> None:
        path = self.root / "cache-marker.txt"
        path.write_text("first", encoding="utf-8")
        calls = []

        def loader():
            calls.append(path.read_text(encoding="utf-8"))
            return calls[-1]

        first = self.service._cached("test-marker", (path,), loader)
        cached = self.service._cached("test-marker", (path,), loader)
        path.write_text("second-value", encoding="utf-8")
        refreshed = self.service._cached("test-marker", (path,), loader)

        self.assertEqual(first, "first")
        self.assertEqual(cached, "first")
        self.assertEqual(refreshed, "second-value")
        self.assertEqual(calls, ["first", "second-value"])

    def test_summary_exposes_audit(
        self,
    ) -> None:
        result = (
            self.service.summary()
        )

        self.assertEqual(
            result["audit"]["status"],
            "PASS",
        )

        self.assertFalse(
            result["audit"][
                "automated_recommendation_ready"
            ]
        )


if __name__ == "__main__":
    unittest.main()
