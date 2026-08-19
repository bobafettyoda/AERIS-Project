from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import pandas as pd

from analysis.parcels.envelope_pipeline import (
    build_scope_envelopes,
    envelope_paths,
    load_yaml,
)


EnvelopeLayer = Literal[
    "development_envelopes",
    "largest_components",
    "scope_constraints",
]


class ParcelEnvelopeService:
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
        return build_scope_envelopes(
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
        return envelope_paths(
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

    def feature_collection(
        self,
        *,
        scope_id: str,
        layer: EnvelopeLayer,
    ) -> dict[str, Any]:
        manifest = self.manifest(
            scope_id
        )

        paths = self._paths(
            scope_id
        )

        if layer not in manifest[
            "written_layers"
        ]:
            return {
                "type": (
                    "FeatureCollection"
                ),
                "features": [],
                "metadata": {
                    "scope_id": scope_id,
                    "layer": layer,
                    "returned_count": 0,
                    "manifest": {
                        "counts": (
                            manifest[
                                "counts"
                            ]
                        ),
                        "status_counts": (
                            manifest[
                                "status_counts"
                            ]
                        ),
                        "safeguards": (
                            manifest[
                                "safeguards"
                            ]
                        ),
                    },
                },
            }

        frame = gpd.read_file(
            paths.output,
            layer=layer,
        )

        simplify_m = (
            float(
                self.config[
                    "api"
                ][
                    "constraint_simplify_m"
                ]
            )
            if layer
            == "scope_constraints"
            else float(
                self.config[
                    "api"
                ][
                    "envelope_simplify_m"
                ]
            )
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

        payload = json.loads(
            frame.to_json(
                drop_id=True,
                na="null",
            )
        )

        payload["metadata"] = {
            "scope_id": scope_id,
            "layer": layer,
            "returned_count": (
                len(frame)
            ),
            "manifest": {
                "counts": (
                    manifest[
                        "counts"
                    ]
                ),
                "status_counts": (
                    manifest[
                        "status_counts"
                    ]
                ),
                "statistics": (
                    manifest[
                        "statistics"
                    ]
                ),
                "constraints": (
                    manifest[
                        "constraints"
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

        return payload

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

        frame = gpd.read_file(
            paths.output,
            layer="parcel_analysis",
        )

        matches = frame.loc[
            frame[
                "parcel_id"
            ].astype(str).eq(
                parcel_id
            )
        ]

        if matches.empty:
            raise KeyError(
                parcel_id
            )

        row = matches.iloc[0]

        def value(
            column: str,
        ) -> Any:
            if column not in row.index:
                return None

            result = row[column]

            try:
                if pd.isna(result):
                    return None
            except (
                TypeError,
                ValueError,
            ):
                pass

            if hasattr(
                result,
                "item",
            ):
                try:
                    return result.item()
                except ValueError:
                    pass

            return result

        return {
            "status": value(
                "envelope_status"
            ),
            "analysis_area_acres": (
                value(
                    "analysis_area_acres"
                )
            ),
            "water_overlap_acres": (
                value(
                    "water_overlap_acres"
                )
            ),
            "protected_lands_overlap_acres": (
                value(
                    "protected_lands_overlap_acres"
                )
            ),
            "sfha_overlap_acres": (
                value(
                    "sfha_overlap_acres"
                )
            ),
            "aviation_overlap_acres": (
                value(
                    "aviation_overlap_acres"
                )
            ),
            "mapped_constrained_area_acres": (
                value(
                    "mapped_constrained_area_acres"
                )
            ),
            "preliminary_unconstrained_area_acres": (
                value(
                    "preliminary_unconstrained_area_acres"
                )
            ),
            "preliminary_unconstrained_fraction": (
                value(
                    "preliminary_unconstrained_fraction"
                )
            ),
            "largest_contiguous_unconstrained_acres": (
                value(
                    "largest_contiguous_unconstrained_acres"
                )
            ),
            "largest_contiguous_fraction": (
                value(
                    "largest_contiguous_fraction"
                )
            ),
            "unconstrained_component_count": (
                value(
                    "unconstrained_component_count"
                )
            ),
            "mapped_constraint_types": (
                value(
                    "mapped_constraint_types"
                )
            ),
            "preliminary_envelope_only": (
                True
            ),
        }
