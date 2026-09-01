from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import pandas as pd

from analysis.common.geojson import feature_collection
from analysis.common.geopackage import read_single_row
from analysis.common.io import load_yaml, read_json
from analysis.common.records import record_value
from analysis.site_feasibility.pipeline import (
    build_site_feasibility,
    site_paths,
)


class SiteFeasibilityService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.config = load_yaml(self.config_path)
        self.project_directory = self.config_path.parents[2]

    def _paths(self, scope_id: str):
        return site_paths(
            config=self.config,
            project_directory=self.project_directory,
            scope_id=scope_id,
        )

    def build(
        self,
        *,
        scope_id: str,
        refresh: bool = False,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> dict[str, Any]:
        return build_site_feasibility(
            config_path=self.config_path,
            scope_id=scope_id,
            refresh=refresh,
            progress_callback=progress_callback,
        )

    def manifest(self, scope_id: str) -> dict[str, Any]:
        path = self._paths(scope_id).manifest
        if not path.exists():
            raise KeyError(scope_id)
        return read_json(path)

    def site_evidence(self, *, scope_id: str) -> dict[str, Any]:
        manifest = self.manifest(scope_id)
        paths = self._paths(scope_id)
        layer_config = self.config["layers"]
        feature_frames: list[gpd.GeoDataFrame] = []
        layer_specs = (
            ("site_envelopes", "site_simplify_m"),
            ("site_constraints", "constraint_simplify_m"),
            ("roads", "road_simplify_m"),
            ("assemblages", "site_simplify_m"),
        )
        for layer_key, simplify_key in layer_specs:
            layer_name = layer_config[layer_key]
            if layer_name not in manifest["written_layers"]:
                continue
            frame = gpd.read_file(paths.output, layer=layer_name)
            simplify_m = float(self.config["api"][simplify_key])
            if simplify_m > 0 and not frame.empty:
                frame.geometry = frame.geometry.simplify(
                    simplify_m,
                    preserve_topology=True,
                )
            feature_frames.append(frame.to_crs("EPSG:4326"))

        if feature_frames:
            combined = gpd.GeoDataFrame(
                pd.concat(
                    feature_frames,
                    ignore_index=True,
                    sort=False,
                ),
                geometry="geometry",
                crs="EPSG:4326",
            )
        else:
            combined = gpd.GeoDataFrame(
                {"geometry": []},
                geometry="geometry",
                crs="EPSG:4326",
            )

        metadata = {
            "scope_id": scope_id,
            "returned_count": len(combined),
            "counts": manifest["counts"],
            "domain_status": manifest["domain_status"],
            "site_feasibility_class_counts": manifest[
                "site_feasibility_class_counts"
            ],
            "top_candidates": manifest.get("top_candidates", []),
            "safeguards": manifest["safeguards"],
            "interpretation": manifest["interpretation"],
        }
        return feature_collection(combined, metadata=metadata)

    def parcel_metrics(
        self,
        *,
        scope_id: str,
        parcel_id: str,
    ) -> dict[str, Any]:
        paths = self._paths(scope_id)
        row = read_single_row(
            paths.output,
            layer=self.config["layers"]["parcel_analysis"],
            key_column="parcel_id",
            key_value=parcel_id,
            read_geometry=False,
        )

        def value(column: str) -> Any:
            return record_value(row, column)

        return {
            "site_feasibility_class": value("site_feasibility_class"),
            "site_candidate_score": value("site_candidate_score"),
            "candidate_eligible": value("candidate_eligible"),
            "candidate_status": value("candidate_status"),
            "candidate_status_reason": value("candidate_status_reason"),
            "base_development_envelope_acres": value(
                "base_development_envelope_acres"
            ),
            "final_site_area_acres": value("final_site_area_acres"),
            "final_site_fraction_of_base_envelope": value(
                "final_site_fraction_of_base_envelope"
            ),
            "largest_contiguous_site_acres": value(
                "largest_contiguous_site_acres"
            ),
            "site_component_count": value("site_component_count"),
            "terrain": {
                "status": value("terrain_data_status"),
                "elevation_minimum_m": value("elevation_minimum_m"),
                "elevation_maximum_m": value("elevation_maximum_m"),
                "elevation_mean_m": value("elevation_mean_m"),
                "elevation_range_m": value("elevation_range_m"),
                "slope_mean_percent": value("slope_mean_percent"),
                "slope_median_percent": value("slope_median_percent"),
                "slope_p90_percent": value("slope_p90_percent"),
                "steep_slope_overlap_acres": value(
                    "steep_slope_overlap_acres"
                ),
                "steep_slope_fraction": value("steep_slope_fraction"),
                "severe_slope_pixel_fraction": value(
                    "terrain_severe_pixel_fraction"
                ),
                "engineering_complete": False,
            },
            "wetlands": {
                "status": value("wetland_data_status"),
                "mapped_overlap_acres": value(
                    "mapped_wetland_overlap_acres"
                ),
                "mapped_overlap_fraction": value(
                    "mapped_wetland_fraction"
                ),
                "special_state_concern_screening_overlap_acres": value(
                    "wssc_screening_overlap_acres"
                ),
                "field_delineation_confirmed": False,
                "permitting_complete": False,
            },
            "road_access": {
                "status": value("road_access_status"),
                "nearest_road_distance_m": value(
                    "nearest_road_distance_m"
                ),
                "nearest_road_name": value("nearest_road_name"),
                "nearest_road_class": value("nearest_road_class"),
                "nearest_primary_road_distance_m": value(
                    "nearest_primary_road_distance_m"
                ),
                "nearest_accessible_road_distance_m": value(
                    "nearest_accessible_road_distance_m"
                ),
                "frontage_proxy_m": value("road_frontage_proxy_m"),
                "limited_access_adjacency_proxy_m": value(
                    "limited_access_adjacency_proxy_m"
                ),
                "site_envelope_to_road_distance_m": value(
                    "site_envelope_to_road_distance_m"
                ),
                "legal_access_confirmed": False,
                "driveway_approval_confirmed": False,
            },
            "existing_development": {
                "building_reference_status": value(
                    "building_reference_status"
                ),
                "building_reference_count": value(
                    "building_reference_count"
                ),
                "building_reference_overlap_acres": value(
                    "building_reference_overlap_acres"
                ),
                "building_reference_fraction": value(
                    "building_reference_fraction"
                ),
                "redevelopment_burden_class": value(
                    "redevelopment_burden_class"
                ),
                "building_geometry_survey_grade": False,
            },
            "safeguards": self.manifest(scope_id)["safeguards"],
            "warning": (
                "This is preliminary physical site-feasibility evidence. "
                "Wetland delineation, survey, grading, legal access, parcel "
                "control, and acquisition feasibility remain unconfirmed."
            ),
        }

    def top_candidates(
        self,
        *,
        scope_id: str,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        candidates = list(self.manifest(scope_id).get("top_candidates", []))
        return candidates[: max(1, min(limit, 100))]

    def compare_candidates(
        self,
        *,
        scope_id: str,
        candidate_ids: list[str],
    ) -> list[dict[str, Any]]:
        requested = {str(value) for value in candidate_ids}
        candidates = self.manifest(scope_id).get("top_candidates", [])
        lookup = {
            str(candidate.get("candidate_id")): candidate
            for candidate in candidates
        }
        missing = sorted(requested - set(lookup))
        if missing:
            raise KeyError(", ".join(missing))
        return [lookup[value] for value in candidate_ids]
