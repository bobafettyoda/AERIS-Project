from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analysis.common.geojson import feature_collection
from analysis.common.geopackage import read_single_row
from analysis.common.records import record_value

import geopandas as gpd
import pandas as pd

from analysis.parcels.pipeline import (
    build_parcel_scope,
    load_config,
    parcel_scope_paths,
    scope_from_bbox,
    scope_from_zone,
)


class ParcelDataService:
    def __init__(
        self,
        config_path: Path,
    ) -> None:
        self.config_path = (
            config_path.resolve()
        )

        self.config = load_config(
            self.config_path
        )

        self.project_directory = (
            self.config_path.parents[2]
        )

    def health(
        self,
    ) -> dict[str, Any]:
        audit_path = (
            self.project_directory
            / self.config[
                "inputs"
            ][
                "source_audit"
            ]["path"]
        )

        final_grid_path = (
            self.project_directory
            / self.config[
                "inputs"
            ][
                "final_grid"
            ]["path"]
        )

        return {
            "ready": (
                audit_path.exists()
                and final_grid_path.exists()
            ),
            "config": str(
                self.config_path
            ),
            "source_audit_exists": (
                audit_path.exists()
            ),
            "final_grid_exists": (
                final_grid_path.exists()
            ),
        }

    def list_scopes(
        self,
    ) -> list[dict[str, Any]]:
        manifest_root = (
            self.project_directory
            / self.config[
                "outputs"
            ][
                "manifest_directory"
            ]["path"]
        )

        if not manifest_root.exists():
            return []

        scopes = []

        for path in sorted(
            manifest_root.glob(
                "*.json"
            )
        ):
            try:
                manifest = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )
            except (
                json.JSONDecodeError,
                OSError,
            ):
                continue

            scopes.append(
                {
                    "scope": (
                        manifest.get(
                            "scope",
                            {},
                        )
                    ),
                    "counts": (
                        manifest.get(
                            "counts",
                            {},
                        )
                    ),
                    "availability_status_counts": (
                        manifest.get(
                            "availability_status_counts",
                            {},
                        )
                    ),
                    "generated_at_utc": (
                        manifest.get(
                            "generated_at_utc"
                        )
                    ),
                }
            )

        return scopes

    def build_zone(
        self,
        *,
        zone_id: str,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return build_parcel_scope(
            config_path=(
                self.config_path
            ),
            zone_id=zone_id,
            refresh=refresh,
        )

    def build_bbox(
        self,
        *,
        west: float,
        south: float,
        east: float,
        north: float,
        scope_name: str | None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return build_parcel_scope(
            config_path=(
                self.config_path
            ),
            bbox=(
                west,
                south,
                east,
                north,
            ),
            scope_name=scope_name,
            refresh=refresh,
        )

    def _manifest(
        self,
        scope_id: str,
    ) -> dict[str, Any]:
        paths = parcel_scope_paths(
            config=self.config,
            project_directory=(
                self.project_directory
            ),
            scope_id=scope_id,
        )

        if not paths.manifest_output.exists():
            raise KeyError(
                scope_id
            )

        return json.loads(
            paths.manifest_output
            .read_text(
                encoding="utf-8"
            )
        )

    def _frame(
        self,
        scope_id: str,
    ) -> gpd.GeoDataFrame:
        paths = parcel_scope_paths(
            config=self.config,
            project_directory=(
                self.project_directory
            ),
            scope_id=scope_id,
        )

        if not paths.normalized_output.exists():
            raise KeyError(
                scope_id
            )

        return gpd.read_file(
            paths.normalized_output,
            layer="parcels",
        )

    def feature_collection(
        self,
        *,
        scope_id: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        manifest = self._manifest(
            scope_id
        )

        frame = self._frame(
            scope_id
        )

        api_config = self.config[
            "api"
        ]

        maximum_features = int(
            api_config[
                "maximum_features"
            ]
        )

        requested_limit = (
            maximum_features
            if limit is None
            else min(
                int(limit),
                maximum_features,
            )
        )

        total_count = len(frame)

        if total_count > (
            requested_limit
        ):
            frame = frame.sort_values(
                [
                    "scope_overlap_fraction",
                    "geometry_area_acres",
                ],
                ascending=[
                    False,
                    False,
                ],
            ).head(
                requested_limit
            )

        fields = [
            field
            for field
            in api_config[
                "display_fields"
            ]
            if field in frame.columns
        ]

        frame = frame[
            [
                *fields,
                "geometry",
            ]
        ].copy()

        simplify_m = float(
            api_config[
                "display_simplify_m"
            ]
        )

        if simplify_m > 0:
            frame.geometry = (
                frame.geometry.simplify(
                    simplify_m,
                    preserve_topology=True,
                )
            )

        frame = frame.to_crs(
            "EPSG:4326"
        )

        metadata = {
            "scope": (
                manifest["scope"]
            ),
            "matching_count": (
                total_count
            ),
            "returned_count": (
                len(frame)
            ),
            "truncated": (
                total_count
                > len(frame)
            ),
            "availability_status_counts": (
                manifest[
                    "availability_status_counts"
                ]
            ),
            "safeguards": (
                manifest[
                    "safeguards"
                ]
            ),
        }

        return feature_collection(frame, metadata=metadata)

    def parcel_detail(
        self,
        *,
        scope_id: str,
        parcel_id: str,
    ) -> dict[str, Any]:
        paths = parcel_scope_paths(
            config=self.config,
            project_directory=self.project_directory,
            scope_id=scope_id,
        )

        row = read_single_row(
            paths.normalized_output,
            layer="parcels",
            key_column="parcel_id",
            key_value=parcel_id,
            read_geometry=False,
        )

        def value(column: str) -> Any:
            return record_value(row, column)

        return {
            "scope_id": scope_id,
            "parcel_id": parcel_id,
            "identity": {
                "account_id": value(
                    "account_id"
                ),
                "jurisdiction_code": (
                    value(
                        "jurisdiction_code"
                    )
                ),
                "county_fips": value(
                    "county_fips"
                ),
                "county_name": value(
                    "county_name"
                ),
                "property_address": (
                    value(
                        "property_address"
                    )
                ),
            },
            "parcel": {
                "parcel_area_acres": (
                    value(
                        "parcel_area_acres"
                    )
                ),
                "source_reported_acres": (
                    value(
                        "source_reported_acres"
                    )
                ),
                "geometry_area_acres": (
                    value(
                        "geometry_area_acres"
                    )
                ),
                "land_use_code": value(
                    "land_use_code"
                ),
                "land_use_description": (
                    value(
                        "land_use_description"
                    )
                ),
                "zoning_code": value(
                    "zoning_code"
                ),
                "commercial_industrial_use": (
                    value(
                        "commercial_industrial_use"
                    )
                ),
                "public_water_status": (
                    value(
                        "public_water_status"
                    )
                ),
                "public_sewer_status": (
                    value(
                        "public_sewer_status"
                    )
                ),
            },
            "source_development_indicators": {
                "year_built": value(
                    "source_year_built"
                ),
                "structure_sq_ft": (
                    value(
                        "source_structure_sq_ft"
                    )
                ),
                "building_units": value(
                    "source_building_units"
                ),
                "building_stories": (
                    value(
                        "source_building_stories"
                    )
                ),
                "appraised_land_value": (
                    value(
                        "appraised_land_value"
                    )
                ),
                "appraised_improvement_value": (
                    value(
                        "appraised_improvement_value"
                    )
                ),
                "appraised_total_value": (
                    value(
                        "appraised_total_value"
                    )
                ),
            },
            "classification": {
                "public_land_flag": bool(
                    value(
                        "public_land_flag"
                    )
                    or False
                ),
                "institutional_use_flag": (
                    bool(
                        value(
                            "institutional_use_flag"
                        )
                        or False
                    )
                ),
                "existing_development_indicator": (
                    bool(
                        value(
                            "existing_development_indicator"
                        )
                        or False
                    )
                ),
                "availability_status": (
                    value(
                        "availability_status"
                    )
                ),
                "availability_reason": (
                    value(
                        "availability_reason"
                    )
                ),
                "availability_confirmed": (
                    False
                ),
                "data_confidence": value(
                    "parcel_data_confidence"
                ),
                "public_classification_evidence": value(
                    "public_classification_evidence"
                ),
                "institutional_classification_evidence": value(
                    "institutional_classification_evidence"
                ),
            },
            "statewide_context": {
                "cell_id": value(
                    "statewide_cell_id"
                ),
                "technical_score": value(
                    "statewide_technical_score"
                ),
                "effective_score": value(
                    "statewide_effective_score"
                ),
                "equity_gate": value(
                    "statewide_equity_gate"
                ),
                "hard_excluded": value(
                    "statewide_hard_excluded"
                ),
                "auto_eligible": value(
                    "statewide_auto_eligible"
                ),
                "exploration_eligible": (
                    value(
                        "statewide_exploration_eligible"
                    )
                ),
            },
            "scope": {
                "candidate_zone_id": (
                    value(
                        "candidate_zone_id"
                    )
                ),
                "candidate_zone_mode": (
                    value(
                        "candidate_zone_mode"
                    )
                ),
                "overlap_fraction": value(
                    "scope_overlap_fraction"
                ),
                "overlap_area_acres": value(
                    "scope_overlap_area_acres"
                ),
                "statewide_link_method": value(
                    "statewide_link_method"
                ),
                "statewide_context_distance_m": value(
                    "statewide_context_distance_m"
                ),
            },
            "source_dates": {
                "polygon_date": value(
                    "source_polygon_date"
                ),
                "property_view_date": (
                    value(
                        "source_property_view_date"
                    )
                ),
                "assessment_date": value(
                    "source_assessment_date"
                ),
                "zoning_change_date": (
                    value(
                        "source_zoning_change_date"
                    )
                ),
            },
            "warning": (
                "Parcel availability, legal "
                "ownership, vacancy, zoning "
                "approval, and buildability "
                "have not been confirmed."
            ),
        }
