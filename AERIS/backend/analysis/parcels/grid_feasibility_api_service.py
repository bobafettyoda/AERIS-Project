from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analysis.common.geopackage import read_single_row
from analysis.common.records import record_value

import geopandas as gpd
import pandas as pd

from analysis.parcels.grid_feasibility_pipeline import (
    build_grid_feasibility,
    grid_feasibility_paths,
    load_yaml,
)


class ParcelGridFeasibilityService:
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

    def build(
        self,
        *,
        scope_id: str,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return build_grid_feasibility(
            config_path=(
                self.config_path
            ),
            scope_id=scope_id,
            refresh=refresh,
        )

    def _paths(
        self,
        scope_id: str,
    ):
        return grid_feasibility_paths(
            config=self.config,
            project_directory=(
                self.project_directory
            ),
            scope_id=scope_id,
        )

    def manifest(
        self,
        scope_id: str,
    ) -> dict[str, Any]:
        paths = self._paths(
            scope_id
        )

        if not paths.manifest.exists():
            raise KeyError(
                scope_id
            )

        return json.loads(
            paths.manifest.read_text(
                encoding="utf-8"
            )
        )

    def grid_evidence(
        self,
        *,
        scope_id: str,
    ) -> dict[str, Any]:
        manifest = self.manifest(
            scope_id
        )

        paths = self._paths(
            scope_id
        )

        layer_config = self.config[
            "layers"
        ]

        features: list[
            dict[str, Any]
        ] = []

        # Browser payload intentionally includes only
        # mapped infrastructure. Parcel-to-feature connector
        # geometries remain in the derived GeoPackage for
        # audit/debug use but are not sent for every parcel.
        for layer_key in (
            "transmission_lines",
            "substations",
        ):
            layer_name = layer_config[
                layer_key
            ]

            if layer_name not in manifest[
                "written_layers"
            ]:
                continue

            frame = gpd.read_file(
                paths.output,
                layer=layer_name,
            )

            if layer_key == (
                "transmission_lines"
            ):
                simplify_m = float(
                    self.config[
                        "api"
                    ][
                        "line_simplify_m"
                    ]
                )

                frame.geometry = (
                    frame.geometry.simplify(
                        simplify_m,
                        preserve_topology=True,
                    )
                )

            frame = frame.to_crs(
                "EPSG:4326"
            )

            features.extend(
                frame.iterfeatures(
                    na="null",
                    show_bbox=False,
                    drop_id=True,
                )
            )

        return {
            "type": (
                "FeatureCollection"
            ),
            "features": features,
            "metadata": {
                "scope_id": scope_id,
                "returned_count": (
                    len(features)
                ),
                "counts": (
                    manifest["counts"]
                ),
                "context_class_counts": (
                    manifest[
                        "context_class_counts"
                    ]
                ),
                "safeguards": (
                    manifest[
                        "safeguards"
                    ]
                ),
                "interpretation": (
                    manifest[
                        "interpretation"
                    ]
                ),
            },
        }

    def parcel_metrics(
        self,
        *,
        scope_id: str,
        parcel_id: str,
    ) -> dict[str, Any]:
        paths = self._paths(
            scope_id
        )

        if not paths.output.exists():
            raise KeyError(
                scope_id
            )

        layer = self.config[
            "layers"
        ]["parcel_analysis"]

        row = read_single_row(
            paths.output,
            layer=layer,
            key_column="parcel_id",
            key_value=parcel_id,
            read_geometry=False,
        )

        def value(column: str) -> Any:
            return record_value(row, column)

        return {
            "grid_feasibility_status": (
                value(
                    "grid_feasibility_status"
                )
            ),
            "public_grid_context_class": (
                value(
                    "public_grid_context_class"
                )
            ),
            "grid_data_confidence": (
                value(
                    "grid_data_confidence"
                )
            ),
            "statewide_grid_infrastructure_score": (
                value(
                    "statewide_grid_infrastructure_score"
                )
            ),
            "nearest_transmission": {
                "distance_m": value(
                    "nearest_transmission_distance_m"
                ),
                "id": value(
                    "nearest_transmission_id"
                ),
                "type": value(
                    "nearest_transmission_type"
                ),
                "status": value(
                    "nearest_transmission_status"
                ),
                "owner": value(
                    "nearest_transmission_owner"
                ),
                "voltage_kv": value(
                    "nearest_transmission_voltage_kv"
                ),
                "voltage_class": value(
                    "nearest_transmission_voltage_class"
                ),
                "source_voltage_class": (
                    value(
                        "nearest_transmission_voltage_class_source"
                    )
                ),
                "inferred": value(
                    "nearest_transmission_inferred"
                ),
                "substation_1": value(
                    "nearest_transmission_substation_1"
                ),
                "substation_2": value(
                    "nearest_transmission_substation_2"
                ),
                "source_date": value(
                    "nearest_transmission_source_date"
                ),
                "validation_method": value(
                    "nearest_transmission_validation_method"
                ),
                "data_confidence": value(
                    "nearest_transmission_data_confidence"
                ),
            },
            "transmission_within_5km": {
                "feature_count": value(
                    "transmission_within_5km_feature_count"
                ),
                "known_voltage_count": value(
                    "transmission_within_5km_known_voltage_count"
                ),
                "maximum_voltage_kv": value(
                    "transmission_within_5km_maximum_voltage_kv"
                ),
                "distinct_owner_count": value(
                    "transmission_within_5km_distinct_owner_count"
                ),
                "owners": value(
                    "transmission_within_5km_owners"
                ),
            },
            "nearest_substation": {
                "distance_m": value(
                    "nearest_substation_distance_m"
                ),
                "id": value(
                    "nearest_substation_id"
                ),
                "name": value(
                    "nearest_substation_name"
                ),
                "type": value(
                    "nearest_substation_type"
                ),
                "status": value(
                    "nearest_substation_status"
                ),
                "line_count": value(
                    "nearest_substation_line_count"
                ),
                "maximum_voltage_kv": value(
                    "nearest_substation_max_voltage_kv"
                ),
                "minimum_voltage_kv": value(
                    "nearest_substation_min_voltage_kv"
                ),
                "voltage_class": value(
                    "nearest_substation_voltage_class"
                ),
                "source_date": value(
                    "nearest_substation_source_date"
                ),
                "validation_method": value(
                    "nearest_substation_validation_method"
                ),
                "data_confidence": value(
                    "nearest_substation_data_confidence"
                ),
            },
            "substations_within_10km": {
                "feature_count": value(
                    "substation_within_10km_feature_count"
                ),
                "known_voltage_count": value(
                    "substation_within_10km_known_voltage_count"
                ),
                "maximum_voltage_kv": value(
                    "substation_within_10km_maximum_voltage_kv"
                ),
            },
            "capacity": {
                "status": value(
                    "capacity_status"
                ),
                "available_capacity_mw": (
                    None
                ),
                "utility_confirmation_required": (
                    True
                ),
                "interconnection_study_required": (
                    True
                ),
                "electrical_service_feasibility_confirmed": (
                    False
                ),
            },
            "warning": (
                "Mapped distance and voltage "
                "do not establish available "
                "utility capacity or an "
                "interconnection path."
            ),
        }
