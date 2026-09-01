from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import rasterio
import yaml
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from analysis.site_feasibility.pipeline import build_site_feasibility
from analysis.site_feasibility.sources import ScopedSourceResult


class SiteFeasibilityPipelineTests(unittest.TestCase):
    def test_full_pipeline_builds_and_filters_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config_directory = project / "configs" / "parcels"
            config_directory.mkdir(parents=True)

            parcel_config = {
                "outputs": {
                    "raw_scope_directory": {"path": "data/raw/parcels"},
                    "cache_directory": {"path": "data/cache/parcels"},
                    "derived_scope_directory": {"path": "data/derived/parcels"},
                    "manifest_directory": {"path": "data/manifests/parcels"},
                }
            }
            envelope_config = {
                "outputs": {
                    "derived_directory": {"path": "data/derived/parcel_envelopes"},
                    "manifest_directory": {"path": "data/manifests/parcel_envelopes"},
                }
            }
            site_config = {
                "schema_version": 1,
                "pipeline_version": "0.7.0-test",
                "snapshot_label": "test",
                "inputs": {
                    "parcel_config": {"path": "configs/parcels/parcels.yaml"},
                    "envelope_config": {"path": "configs/parcels/envelopes.yaml"},
                    "terrain": {
                        "enabled": True,
                        "image_server_url": "https://example.invalid/ImageServer",
                        "source_name": "Synthetic DEM",
                        "source_last_updated": "test",
                        "dem_raster_function": "None",
                        "target_pixel_size_m": 10.0,
                        "maximum_pixel_size_m": 30.0,
                        "maximum_total_pixels": 1_000_000,
                        "maximum_tile_pixels": 1000,
                        "timeout_seconds": 30,
                        "steep_slope_threshold_percent": 15.0,
                        "severe_slope_threshold_percent": 25.0,
                        "minimum_polygon_area_acres": 0.01,
                        "subtract_steep_slope_from_site_envelope": True,
                    },
                    "wetlands": {
                        "enabled": True,
                        "service_url": "https://example.invalid/wetlands",
                        "page_size": 100,
                        "timeout_seconds": 30,
                        "scope_buffer_m": 0.0,
                        "layers": {
                            "dnr_polygon": {
                                "id": 1,
                                "name": "Synthetic wetland",
                                "where": "Type IN ('Palustrine')",
                                "fields": ["OBJECTID"],
                                "subtract_from_site_envelope": True,
                            },
                            "national_wetlands_inventory": {
                                "id": 2,
                                "name": "Synthetic NWI",
                                "fields": ["OBJECTID"],
                                "subtract_from_site_envelope": True,
                            },
                            "special_state_concern": {
                                "id": 3,
                                "name": "Synthetic WSSC",
                                "fields": ["OBJECTID"],
                                "buffer_m": 30.48,
                                "subtract_from_site_envelope": True,
                            },
                        },
                    },
                    "roads": {
                        "enabled": True,
                        "service_url": "https://example.invalid/roads",
                        "page_size": 100,
                        "timeout_seconds": 30,
                        "scope_buffer_m": 100.0,
                        "frontage_tolerance_m": 10.0,
                        "minimum_frontage_proxy_m": 15.0,
                        "direct_frontage_excluded_classes": ["INTERSTATE"],
                        "near_road_threshold_m": 100.0,
                        "remote_road_threshold_m": 500.0,
                        "layers": {
                            "interstate": {"id": 0, "rank": 1},
                            "local_other": {"id": 3, "rank": 4},
                        },
                        "fields": [
                            "OBJECTID",
                            "ROADNAMESHA",
                            "ID_PREFIX",
                            "ID_RTE_NO",
                            "ROUTEID",
                            "ROUTEID_RH",
                            "CENTERLINEID",
                        ],
                    },
                    "buildings": {
                        "enabled": True,
                        "layer_url": "https://example.invalid/buildings/0",
                        "source_name": "Synthetic buildings",
                        "source_role": "reference_only",
                        "page_size": 100,
                        "timeout_seconds": 30,
                        "scope_buffer_m": 0.0,
                        "maximum_scope_features": 100,
                        "subtract_from_site_envelope": False,
                    },
                },
                "analysis": {
                    "target_crs": "EPSG:26985",
                    "square_meters_per_acre": 4046.8564224,
                    "geometry_precision_m": 0.1,
                    "minimum_site_component_acres": 0.25,
                    "assemblages": {
                        "enabled": True,
                        "adjacency_gap_m": 8.0,
                        "minimum_parcel_site_acres": 2.0,
                        "minimum_total_site_acres": 10.0,
                        "minimum_parcel_count": 2,
                        "maximum_parcel_count": 40,
                        "maximum_candidates": 100,
                    },
                    "candidate_classes": {
                        "strong": {
                            "largest_contiguous_acres": 50.0,
                            "maximum_steep_fraction": 0.10,
                            "maximum_wetland_fraction": 0.02,
                            "maximum_building_fraction": 0.05,
                            "road_access": ["DIRECT_MAPPED_ROAD_FRONTAGE_PROXY"],
                        },
                        "promising": {
                            "largest_contiguous_acres": 25.0,
                            "maximum_steep_fraction": 0.25,
                            "maximum_wetland_fraction": 0.10,
                            "road_access": [
                                "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
                                "NEAR_MAPPED_PUBLIC_ROAD",
                            ],
                        },
                        "limited_minimum_acres": 5.0,
                    },
                },
                "outputs": {
                    "raw_scope_directory": {"path": "data/raw/site_feasibility"},
                    "cache_directory": {"path": "data/cache/site_feasibility"},
                    "derived_directory": {"path": "data/derived/parcel_site_feasibility"},
                    "manifest_directory": {"path": "data/manifests/parcel_site_feasibility"},
                },
                "layers": {
                    "parcel_analysis": "parcel_site_analysis",
                    "site_envelopes": "site_envelopes",
                    "largest_components": "largest_site_components",
                    "site_constraints": "site_constraints",
                    "roads": "site_roads",
                    "buildings_reference": "site_buildings_reference",
                    "assemblages": "site_assemblages",
                },
                "api": {
                    "site_simplify_m": 0.75,
                    "constraint_simplify_m": 1.0,
                    "road_simplify_m": 1.5,
                    "building_simplify_m": 0.75,
                    "maximum_top_candidates": 100,
                },
                "safeguards": {
                    "legal_buildability_confirmed": False,
                    "wetland_delineation_confirmed": False,
                    "road_access_confirmed": False,
                    "parcel_assembly_control_confirmed": False,
                },
            }

            (config_directory / "parcels.yaml").write_text(
                yaml.safe_dump(parcel_config),
                encoding="utf-8",
            )
            (config_directory / "envelopes.yaml").write_text(
                yaml.safe_dump(envelope_config),
                encoding="utf-8",
            )
            site_config_path = config_directory / "site.yaml"
            site_config_path.write_text(
                yaml.safe_dump(site_config),
                encoding="utf-8",
            )

            scope_id = "synthetic-scope"
            parcel_path = project / "data" / "derived" / "parcels" / f"{scope_id}.gpkg"
            parcel_path.parent.mkdir(parents=True)
            parcels = gpd.GeoDataFrame(
                {
                    "parcel_id": ["ELIGIBLE", "PUBLIC"],
                    "geometry_area_acres": [61.8, 61.8],
                    "public_land_flag": [False, True],
                    "institutional_use_flag": [False, False],
                    "statewide_hard_excluded": [False, False],
                    "existing_development_indicator": [False, False],
                    "source_structure_sq_ft": [0.0, 0.0],
                    "appraised_improvement_value": [0.0, 0.0],
                },
                geometry=[
                    box(0, 0, 500, 500),
                    box(501, 0, 1001, 500),
                ],
                crs="EPSG:26985",
            )
            parcels.to_file(parcel_path, layer="parcels", driver="GPKG", index=False)

            envelope_path = (
                project
                / "data"
                / "derived"
                / "parcel_envelopes"
                / f"{scope_id}.gpkg"
            )
            envelope_path.parent.mkdir(parents=True)
            parcels[["parcel_id", "geometry"]].to_file(
                envelope_path,
                layer="development_envelopes",
                driver="GPKG",
                index=False,
            )

            def scoped_source(**kwargs):
                source_id = str(kwargs["source_id"])
                if source_id == "wetlands_dnr_polygon":
                    self.assertEqual(
                        kwargs.get("where"),
                        "Type IN ('Palustrine')",
                    )
                    frame = gpd.GeoDataFrame(
                        {"OBJECTID": [1]},
                        geometry=[box(20, 20, 50, 50)],
                        crs="EPSG:26985",
                    )
                elif source_id.startswith("wetlands_"):
                    frame = gpd.GeoDataFrame(
                        {"geometry": []},
                        geometry="geometry",
                        crs="EPSG:26985",
                    )
                elif source_id == "roads_local_other":
                    frame = gpd.GeoDataFrame(
                        {
                            "OBJECTID": [1],
                            "ROADNAMESHA": ["Local Road"],
                            "ID_PREFIX": [""],
                            "ID_RTE_NO": [""],
                            "ROUTEID": ["LOCAL-1"],
                            "ROUTEID_RH": ["LOCAL-1"],
                            "CENTERLINEID": ["LOCAL-1"],
                        },
                        geometry=[LineString([(0, -5), (1001, -5)])],
                        crs="EPSG:26985",
                    )
                elif source_id == "roads_interstate":
                    frame = gpd.GeoDataFrame(
                        {
                            "OBJECTID": [2],
                            "ROADNAMESHA": ["Interstate"],
                            "ID_PREFIX": ["IS"],
                            "ID_RTE_NO": ["95"],
                            "ROUTEID": ["I-95"],
                            "ROUTEID_RH": ["I-95"],
                            "CENTERLINEID": ["I-95"],
                        },
                        geometry=[LineString([(0, 510), (1001, 510)])],
                        crs="EPSG:26985",
                    )
                elif source_id == "buildings_reference":
                    frame = gpd.GeoDataFrame(
                        {"OBJECTID": [3]},
                        geometry=[box(100, 100, 120, 120)],
                        crs="EPSG:26985",
                    )
                else:
                    raise AssertionError(source_id)
                return ScopedSourceResult(
                    source_id=source_id,
                    frame=frame,
                    metadata={
                        "source_id": source_id,
                        "snapshot_feature_count": len(frame),
                        "empty": frame.empty,
                    },
                )

            def terrain_export(*, paths, bounds, **kwargs):
                del kwargs
                west, south, east, north = bounds
                width = int(np.ceil((east - west) / 10.0))
                height = int(np.ceil((north - south) / 10.0))
                transform = from_origin(west, north, 10.0, 10.0)
                profile = {
                    "driver": "GTiff",
                    "height": height,
                    "width": width,
                    "count": 1,
                    "dtype": "float32",
                    "crs": "EPSG:26985",
                    "transform": transform,
                    "nodata": np.nan,
                }
                paths.dem.parent.mkdir(parents=True, exist_ok=True)
                with rasterio.open(paths.dem, "w", **profile) as dataset:
                    dataset.write(np.zeros((height, width), dtype="float32"), 1)
                with rasterio.open(paths.slope, "w", **profile) as dataset:
                    dataset.write(np.zeros((height, width), dtype="float32"), 1)
                metadata = {
                    "source_name": "Synthetic DEM",
                    "bounds": list(bounds),
                    "pixel_size_m": 10.0,
                    "used_cache": False,
                }
                paths.metadata.write_text(json.dumps(metadata), encoding="utf-8")
                return metadata

            progress_events: list[tuple[str, float]] = []
            with patch(
                "analysis.site_feasibility.pipeline.download_scoped_layer",
                side_effect=scoped_source,
            ), patch(
                "analysis.site_feasibility.pipeline.export_scope_terrain",
                side_effect=terrain_export,
            ):
                manifest = build_site_feasibility(
                    config_path=site_config_path,
                    scope_id=scope_id,
                    progress_callback=lambda stage, progress: progress_events.append(
                        (stage, progress)
                    ),
                )

            output_path = project / manifest["outputs"]["geopackage"]
            analysis = gpd.read_file(output_path, layer="parcel_site_analysis")
            eligible = analysis.set_index("parcel_id").loc["ELIGIBLE"]
            public = analysis.set_index("parcel_id").loc["PUBLIC"]

            self.assertTrue(bool(eligible["candidate_eligible"]))
            self.assertEqual(
                eligible["candidate_status"],
                "PRELIMINARY_PHYSICAL_COMPARISON_CANDIDATE",
            )
            self.assertFalse(bool(public["candidate_eligible"]))
            self.assertEqual(
                public["candidate_status"],
                "INELIGIBLE_PUBLIC_OR_INSTITUTIONAL",
            )
            self.assertEqual(
                eligible["road_access_status"],
                "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY",
            )
            self.assertGreater(float(eligible["final_site_area_acres"]), 50)
            self.assertEqual(
                [candidate["candidate_id"] for candidate in manifest["top_candidates"]],
                ["ELIGIBLE"],
            )
            self.assertEqual(progress_events[0][0], "loading_inputs")
            self.assertEqual(progress_events[-1], ("complete", 1.0))
            self.assertIn("terrain", {stage for stage, _ in progress_events})


if __name__ == "__main__":
    unittest.main()
