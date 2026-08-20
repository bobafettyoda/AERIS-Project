from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analysis.common.geopackage import read_single_row
from analysis.common.records import record_value

import geopandas as gpd
import pandas as pd

from analysis.common.geojson import feature_collection

from analysis.planning.planning_pipeline import (
    build_planning_context,
    load_yaml,
    output_paths,
)
from analysis.planning.registry import (
    PlanningRegistry,
)


class PlanningContextService:
    def __init__(
        self,
        config_path: Path,
    ) -> None:
        self.config_path = (
            config_path.resolve()
        )

        self.config = load_yaml(
            self.config_path
        )

        self.project_directory = (
            self.config_path.parents[2]
        )

        self.registry = PlanningRegistry(
            self.project_directory
            / self.config[
                "registry"
            ]["path"]
        )

    def build(
        self,
        *,
        scope_id: str,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return build_planning_context(
            config_path=(
                self.config_path
            ),
            scope_id=scope_id,
            refresh=refresh,
        )

    def _paths(
        self,
        scope_id: str,
    ) -> tuple[
        Path,
        Path,
    ]:
        return output_paths(
            config=self.config,
            project_directory=(
                self.project_directory
            ),
            scope_id=scope_id,
        )

    def registry_summary(
        self,
    ) -> dict[str, Any]:
        return (
            self.registry
            .coverage_summary()
        )

    def overlays(
        self,
        *,
        scope_id: str,
    ) -> dict[str, Any]:
        output_path, manifest_path = (
            self._paths(
                scope_id
            )
        )

        if not (
            output_path.exists()
            and manifest_path.exists()
        ):
            raise KeyError(
                scope_id
            )

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        layer_name = self.config[
            "layers"
        ]["context_overlays"]

        frame = gpd.read_file(
            output_path,
            layer=layer_name,
        )

        simplify_m = float(
            self.config[
                "api"
            ][
                "overlay_simplify_m"
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
            "scope_id": scope_id,
            "returned_count": (
                len(frame)
            ),
            "counts": (
                manifest["counts"]
            ),
            "planning_review_status_counts": (
                manifest[
                    "planning_review_status_counts"
                ]
            ),
            "registry_coverage": (
                manifest[
                    "registry_coverage"
                ]
            ),
            "safeguards": (
                manifest[
                    "safeguards"
                ]
            ),
        }

        return feature_collection(frame, metadata=metadata)

    def parcel_metrics(
        self,
        *,
        scope_id: str,
        parcel_id: str,
    ) -> dict[str, Any]:
        output_path, _ = (
            self._paths(
                scope_id
            )
        )

        if not output_path.exists():
            raise KeyError(
                scope_id
            )

        row = read_single_row(
            output_path,
            layer=self.config["layers"]["parcel_analysis"],
            key_column="parcel_id",
            key_value=parcel_id,
            read_geometry=False,
        )

        def value(column: str) -> Any:
            return record_value(row, column)

        return {
            "jurisdiction": {
                "county_fips": value(
                    "county_fips"
                ),
                "county_name": value(
                    "county_name"
                ),
                "municipality_name": value("municipality_name"),
                "municipality_overlap_acres": value("municipality_overlap_acres"),
                "municipality_overlap_fraction": value("municipality_overlap_fraction"),
                "municipality_assignment_method": value("municipality_assignment_method"),
                "authority_profile": (
                    value(
                        "authority_profile"
                    )
                ),
                "authority_level": value(
                    "planning_authority_level"
                ),
                "authority_name": value(
                    "planning_authority_name"
                ),
                "authority_status": value(
                    "planning_authority_status"
                ),
            },
            "zoning": {
                "statewide_code": value(
                    "zoning_code"
                ),
                "statewide_status": value(
                    "statewide_zoning_status"
                ),
                "local_source_status": (
                    value(
                        "local_zoning_source_status"
                    )
                ),
                "local_source_note": value(
                    "local_zoning_source_note"
                ),
                "local_verified": False,
                "permitted_use_determined": (
                    False
                ),
            },
            "planning_sources": {
                "comprehensive_plan": value(
                    "comprehensive_plan_source_status"
                ),
                "active_development": value(
                    "active_development_source_status"
                ),
                "permits": value(
                    "permit_source_status"
                ),
            },
            "adapter": {
                "name": value("planning_adapter_name"),
                "available": bool(value("planning_adapter_available") or False),
                "zoning_status": value("planning_adapter_zoning_status"),
                "active_development_status": value(
                    "planning_adapter_active_development_status"
                ),
                "permit_status": value("planning_adapter_permit_status"),
                "warning": value("planning_adapter_warning"),
            },
            "statewide_context": {
                "priority_funding_area": value("pfa_status"),
                "priority_funding_area_overlap_acres": value("pfa_overlap_acres"),
                "priority_funding_area_overlap_fraction": value("pfa_overlap_fraction"),
                "priority_funding_area_assignment_method": value("pfa_assignment_method"),
                "critical_area_overlap": (
                    bool(
                        value(
                            "critical_area_overlap"
                        )
                        or False
                    )
                ),
                "critical_area_overlap_acres": (
                    value(
                        "critical_area_overlap_acres"
                    )
                ),
                "enterprise_zone_count": value(
                    "enterprise_zone_feature_count"
                ),
                "enterprise_zone_names": value(
                    "enterprise_zone_names"
                ),
                "sustainable_community_count": (
                    value(
                        "sustainable_community_feature_count"
                    )
                ),
                "sustainable_community_names": (
                    value(
                        "sustainable_community_names"
                    )
                ),
                "foreign_trade_zone_count": (
                    value(
                        "foreign_trade_zone_feature_count"
                    )
                ),
                "foreign_trade_zone_names": (
                    value(
                        "foreign_trade_zone_names"
                    )
                ),
                "rise_zone_count": value(
                    "rise_zone_feature_count"
                ),
                "rise_zone_names": value(
                    "rise_zone_names"
                ),
                "opportunity_zone_count": (
                    value(
                        "opportunity_zone_feature_count"
                    )
                ),
                "opportunity_zone_names": (
                    value(
                        "opportunity_zone_names"
                    )
                ),
            },
            "decision": {
                "planning_review_status": (
                    value(
                        "planning_review_status"
                    )
                ),
                "data_confidence": value(
                    "planning_data_confidence"
                ),
                "manual_local_verification_required": (
                    True
                ),
                "active_development_clear": (
                    False
                ),
                "permit_clearance_determined": (
                    False
                ),
                "entitlement_clearance_determined": (
                    False
                ),
            },
            "warning": (
                "Statewide planning context "
                "does not establish permitted "
                "use, zoning approval, absence "
                "of active development, or "
                "entitlement clearance."
            ),
        }
