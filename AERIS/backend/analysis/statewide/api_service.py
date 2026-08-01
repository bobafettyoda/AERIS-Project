from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio


ScoreType = Literal[
    "technical",
    "effective",
]

EligibilityType = Literal[
    "all",
    "auto",
    "exploration",
]

ZoneMode = Literal[
    "top",
    "auto",
    "exploration",
]


MARYLAND_COUNTIES = {
    "001": "Allegany County",
    "003": "Anne Arundel County",
    "005": "Baltimore County",
    "009": "Calvert County",
    "011": "Caroline County",
    "013": "Carroll County",
    "015": "Cecil County",
    "017": "Charles County",
    "019": "Dorchester County",
    "021": "Frederick County",
    "023": "Garrett County",
    "025": "Harford County",
    "027": "Howard County",
    "029": "Kent County",
    "031": "Montgomery County",
    "033": "Prince George's County",
    "035": "Queen Anne's County",
    "037": "St. Mary's County",
    "039": "Somerset County",
    "041": "Talbot County",
    "043": "Washington County",
    "045": "Wicomico County",
    "047": "Worcester County",
    "510": "Baltimore City",
}


@dataclass(frozen=True)
class StatewidePaths:
    root: Path
    final_grid: Path
    final_preview: Path
    auto_zones: Path
    exploration_zones: Path
    top_zones: Path
    zone_membership: Path
    final_manifest: Path
    candidate_manifest: Path
    bias_audit: Path
    score_bands: Path

    @classmethod
    def from_root(
        cls,
        root: Path,
    ) -> StatewidePaths:
        root = root.expanduser().resolve()

        data = root / "data"

        return cls(
            root=root,
            final_grid=(
                data
                / "derived"
                / "maryland_grid_1km_final.gpkg"
            ),
            final_preview=(
                data
                / "derived"
                / "maryland_grid_1km_final_points.geojson"
            ),
            auto_zones=(
                data
                / "derived"
                / "maryland_candidate_zones_auto.gpkg"
            ),
            exploration_zones=(
                data
                / "derived"
                / "maryland_candidate_zones_exploration.gpkg"
            ),
            top_zones=(
                data
                / "derived"
                / "maryland_candidate_zones_top5.geojson"
            ),
            zone_membership=(
                data
                / "derived"
                / "maryland_candidate_zone_membership.csv"
            ),
            final_manifest=(
                data
                / "manifests"
                / "statewide_climate_final.json"
            ),
            candidate_manifest=(
                data
                / "manifests"
                / "statewide_candidate_zones.json"
            ),
            bias_audit=(
                data
                / "manifests"
                / "statewide_bias_audit.json"
            ),
            score_bands=(
                data
                / "manifests"
                / "statewide_score_band_summary.json"
            ),
        )

    @classmethod
    def from_environment(
        cls,
    ) -> StatewidePaths:
        default_root = (
            Path(__file__)
            .resolve()
            .parents[3]
        )

        configured = os.getenv(
            "AERIS_PROJECT_ROOT",
            str(default_root),
        )

        return cls.from_root(
            Path(configured)
        )


def json_scalar(
    value: Any,
) -> Any:
    if isinstance(
        value,
        np.generic,
    ):
        value = value.item()

    if isinstance(
        value,
        pd.Timestamp,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Path,
    ):
        return str(value)

    try:
        if pd.isna(value):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): json_scalar(child)
            for key, child
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            json_scalar(child)
            for child in value
        ]

    return value


def bool_series(
    values: pd.Series,
) -> pd.Series:
    if pd.api.types.is_bool_dtype(
        values
    ):
        return values.fillna(False)

    if pd.api.types.is_numeric_dtype(
        values
    ):
        return (
            pd.to_numeric(
                values,
                errors="coerce",
            )
            .fillna(0)
            .ne(0)
        )

    return (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
        .isin(
            {
                "1",
                "true",
                "t",
                "yes",
                "y",
            }
        )
    )


def bool_value(
    value: Any,
) -> bool:
    return bool(
        bool_series(
            pd.Series([value])
        ).iloc[0]
    )


def standardize_identifier(
    values: pd.Series,
    width: int,
) -> pd.Series:
    return (
        values.astype("string")
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.strip()
        .str.zfill(width)
    )


class StatewideDataService:
    def __init__(
        self,
        paths: StatewidePaths,
    ) -> None:
        self.paths = paths

    def required_files(
        self,
    ) -> dict[str, Path]:
        return {
            "final_grid": (
                self.paths.final_grid
            ),
            "final_preview": (
                self.paths.final_preview
            ),
            "auto_zones": (
                self.paths.auto_zones
            ),
            "exploration_zones": (
                self.paths.exploration_zones
            ),
            "top_zones": (
                self.paths.top_zones
            ),
            "zone_membership": (
                self.paths.zone_membership
            ),
            "final_manifest": (
                self.paths.final_manifest
            ),
            "candidate_manifest": (
                self.paths.candidate_manifest
            ),
            "bias_audit": (
                self.paths.bias_audit
            ),
            "score_bands": (
                self.paths.score_bands
            ),
        }

    def health(
        self,
    ) -> dict[str, Any]:
        files = {
            name: {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": (
                    path.stat().st_size
                    if path.exists()
                    else 0
                ),
            }
            for name, path
            in self.required_files().items()
        }

        return {
            "ready": all(
                item["exists"]
                for item in files.values()
            ),
            "root": str(
                self.paths.root
            ),
            "files": files,
        }

    @staticmethod
    def _require(
        path: Path,
    ) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Required statewide file "
                f"does not exist: {path}"
            )

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        StatewideDataService._require(
            path
        )

        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            value,
            dict,
        ):
            raise RuntimeError(
                f"Expected a JSON object: {path}"
            )

        return value

    @lru_cache(maxsize=1)
    def final_grid(
        self,
    ) -> pd.DataFrame:
        self._require(
            self.paths.final_grid
        )

        frame = pyogrio.read_dataframe(
            self.paths.final_grid,
            layer="cells",
            read_geometry=False,
        )

        if "cell_id" not in frame:
            raise RuntimeError(
                "Final statewide grid "
                "does not contain cell_id."
            )

        frame["cell_id"] = (
            frame["cell_id"]
            .astype("string")
        )

        if "county" in frame:
            county_fips = (
                standardize_identifier(
                    frame["county"],
                    3,
                )
            )

        elif "COUNTYFP" in frame:
            county_fips = (
                standardize_identifier(
                    frame["COUNTYFP"],
                    3,
                )
            )

        elif "GEOID" in frame:
            county_fips = (
                standardize_identifier(
                    frame["GEOID"],
                    11,
                ).str.slice(2, 5)
            )

        else:
            county_fips = pd.Series(
                "UNK",
                index=frame.index,
                dtype="string",
            )

        frame["county_fips"] = (
            county_fips
        )

        frame["county_name"] = (
            county_fips.map(
                MARYLAND_COUNTIES
            ).fillna(
                "Unknown county"
            )
        )

        return frame

    @lru_cache(maxsize=1)
    def grid_preview(
        self,
    ) -> gpd.GeoDataFrame:
        self._require(
            self.paths.final_preview
        )

        frame = gpd.read_file(
            self.paths.final_preview
        )

        if frame.crs is None:
            frame = frame.set_crs(
                "EPSG:4326"
            )

        elif str(frame.crs) != "EPSG:4326":
            frame = frame.to_crs(
                "EPSG:4326"
            )

        if "cell_id" not in frame:
            raise RuntimeError(
                "Statewide preview does not "
                "contain cell_id."
            )

        frame["cell_id"] = (
            frame["cell_id"]
            .astype("string")
        )

        index = self.final_grid()[
            [
                "cell_id",
                "county_fips",
                "county_name",
            ]
        ]

        frame = frame.drop(
            columns=[
                "county_fips",
                "county_name",
            ],
            errors="ignore",
        ).merge(
            index,
            how="left",
            on="cell_id",
            validate="one_to_one",
        )

        return gpd.GeoDataFrame(
            frame,
            geometry="geometry",
            crs="EPSG:4326",
        )

    @lru_cache(maxsize=3)
    def zones(
        self,
        mode: ZoneMode,
    ) -> gpd.GeoDataFrame:
        if mode == "top":
            path = self.paths.top_zones
            layer = None

        elif mode == "auto":
            path = self.paths.auto_zones
            layer = "candidate_zones"

        else:
            path = (
                self.paths.exploration_zones
            )
            layer = "candidate_zones"

        self._require(path)

        if layer is None:
            frame = gpd.read_file(path)
        else:
            frame = gpd.read_file(
                path,
                layer=layer,
            )

        if frame.crs is None:
            frame = frame.set_crs(
                "EPSG:4326"
            )

        elif str(frame.crs) != "EPSG:4326":
            frame = frame.to_crs(
                "EPSG:4326"
            )

        return frame

    @lru_cache(maxsize=1)
    def membership(
        self,
    ) -> pd.DataFrame:
        self._require(
            self.paths.zone_membership
        )

        frame = pd.read_csv(
            self.paths.zone_membership,
            dtype={
                "mode": "string",
                "zone_id": "string",
                "cell_id": "string",
            },
        )

        return frame

    def summary(
        self,
    ) -> dict[str, Any]:
        final_manifest = self._read_json(
            self.paths.final_manifest
        )

        candidate_manifest = (
            self._read_json(
                self.paths.candidate_manifest
            )
        )

        audit = self._read_json(
            self.paths.bias_audit
        )

        score_bands = self._read_json(
            self.paths.score_bands
        )

        preview = self.grid_preview()

        west, south, east, north = (
            float(value)
            for value
            in preview.total_bounds
        )

        counties = (
            self.final_grid()[
                [
                    "county_fips",
                    "county_name",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                "county_name"
            )
        )

        return {
            "project": "AERIS",
            "analysis": (
                "Maryland statewide "
                "data-center screening"
            ),
            "model_version": (
                final_manifest.get(
                    "snapshot_label"
                )
            ),
            "grid": {
                "cell_count": (
                    final_manifest[
                        "final_model"
                    ]["cell_count"]
                ),
                "complete_cells": (
                    final_manifest[
                        "final_model"
                    ]["complete_cells"]
                ),
                "insufficient_data_cells": (
                    final_manifest[
                        "final_model"
                    ][
                        "insufficient_data_cells"
                    ]
                ),
                "hard_excluded_cells": (
                    final_manifest[
                        "final_model"
                    ]["hard_excluded_cells"]
                ),
                "auto_screen_eligible_cells": (
                    final_manifest[
                        "final_model"
                    ][
                        "auto_screen_eligible_cells"
                    ]
                ),
                "exploration_screen_eligible_cells": (
                    final_manifest[
                        "final_model"
                    ][
                        "exploration_screen_eligible_cells"
                    ]
                ),
            },
            "zones": (
                candidate_manifest.get(
                    "counts",
                    {},
                )
            ),
            "audit": {
                "status": (
                    audit.get(
                        "audit_status"
                    )
                ),
                "release_status": (
                    audit.get(
                        "release_status"
                    )
                ),
                "screening_shortlist_ready": (
                    audit.get(
                        "screening_shortlist_ready"
                    )
                ),
                "automated_recommendation_ready": (
                    audit.get(
                        "automated_recommendation_ready",
                        False,
                    )
                ),
                "material_flags": (
                    audit.get(
                        "material_flags",
                        {},
                    )
                ),
            },
            "score_statistics": (
                final_manifest[
                    "final_model"
                ][
                    "technical_score_statistics"
                ]
            ),
            "effective_score_statistics": (
                final_manifest[
                    "final_model"
                ][
                    "effective_score_statistics"
                ]
            ),
            "score_bands": (
                score_bands.get(
                    "score_bands",
                    [],
                )
            ),
            "bounds": {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
            },
            "counties": [
                {
                    "fips": str(
                        row[
                            "county_fips"
                        ]
                    ),
                    "name": str(
                        row[
                            "county_name"
                        ]
                    ),
                }
                for _, row
                in counties.iterrows()
                if str(
                    row["county_fips"]
                ) != "UNK"
            ],
            "terminology": (
                candidate_manifest.get(
                    "terminology",
                    {},
                )
            ),
            "required_next_stage": (
                candidate_manifest.get(
                    "required_next_stage",
                    [],
                )
            ),
        }

    @staticmethod
    def _feature_collection(
        frame: gpd.GeoDataFrame,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if frame.crs is None:
            frame = frame.set_crs(
                "EPSG:4326"
            )

        elif str(frame.crs) != "EPSG:4326":
            frame = frame.to_crs(
                "EPSG:4326"
            )

        payload = json.loads(
            frame.to_json(
                drop_id=True,
                na="null",
            )
        )

        payload["metadata"] = (
            json_scalar(metadata)
        )

        return payload

    def grid_feature_collection(
        self,
        *,
        score_type: ScoreType = (
            "technical"
        ),
        minimum_score: float = 0.0,
        maximum_score: float = 1.0,
        eligibility: EligibilityType = (
            "all"
        ),
        equity_gates: list[str] | None = None,
        excluded: bool | None = None,
        county: str | None = None,
        limit: int = 30000,
    ) -> dict[str, Any]:
        if minimum_score > maximum_score:
            raise ValueError(
                "minimum_score cannot exceed "
                "maximum_score."
            )

        frame = self.grid_preview().copy()

        score_column = (
            "technical_suitability_score"
            if score_type == "technical"
            else "effective_suitability_score"
        )

        if score_column not in frame:
            raise RuntimeError(
                f"Preview is missing "
                f"{score_column}."
            )

        score = pd.to_numeric(
            frame[score_column],
            errors="coerce",
        )

        mask = score.between(
            minimum_score,
            maximum_score,
            inclusive="both",
        )

        if eligibility == "auto":
            mask &= bool_series(
                frame[
                    "auto_screen_eligible"
                ]
            )

        elif eligibility == (
            "exploration"
        ):
            mask &= bool_series(
                frame[
                    "exploration_screen_eligible"
                ]
            )

        if equity_gates:
            normalized_gates = {
                str(value).strip().upper()
                for value in equity_gates
            }

            mask &= (
                frame["equity_gate"]
                .astype("string")
                .str.upper()
                .isin(
                    normalized_gates
                )
            )

        if excluded is not None:
            mask &= (
                bool_series(
                    frame[
                        "hard_excluded"
                    ]
                )
                == excluded
            )

        if county:
            county_key = (
                county.strip().casefold()
            )

            county_fips = (
                county.strip().zfill(3)
            )

            mask &= (
                frame[
                    "county_fips"
                ].astype(str).eq(
                    county_fips
                )
                | frame[
                    "county_name"
                ].astype(str)
                .str.casefold()
                .str.contains(
                    county_key,
                    regex=False,
                )
            )

        filtered = frame.loc[
            mask
        ].copy()

        filtered[
            "display_score"
        ] = pd.to_numeric(
            filtered[score_column],
            errors="coerce",
        )

        total_matching = len(filtered)

        if (
            limit > 0
            and len(filtered) > limit
        ):
            filtered = (
                filtered.sort_values(
                    "display_score",
                    ascending=False,
                )
                .head(limit)
            )

        fields = [
            "cell_id",
            "display_score",
            "technical_suitability_score",
            "effective_suitability_score",
            "hard_excluded",
            "final_model_status",
            "equity_gate",
            "auto_screen_eligible",
            "exploration_screen_eligible",
            "county_fips",
            "county_name",
            "climate_score",
            "grid_infrastructure_score",
            "telecom_infrastructure_score",
            "protected_areas_score",
            "water_bodies_score",
            "population_density_score",
            "road_access_score",
            "hydro_hazard_score",
            "geometry",
        ]

        fields = [
            field
            for field in fields
            if field in filtered.columns
        ]

        filtered = gpd.GeoDataFrame(
            filtered[fields],
            geometry="geometry",
            crs=frame.crs,
        )

        return self._feature_collection(
            filtered,
            {
                "score_type": score_type,
                "score_column": (
                    score_column
                ),
                "minimum_score": (
                    minimum_score
                ),
                "maximum_score": (
                    maximum_score
                ),
                "eligibility": (
                    eligibility
                ),
                "equity_gates": (
                    equity_gates or []
                ),
                "excluded": excluded,
                "county": county,
                "matching_count": (
                    total_matching
                ),
                "returned_count": (
                    len(filtered)
                ),
                "limit": limit,
            },
        )

    def zone_feature_collection(
        self,
        *,
        mode: ZoneMode,
        minimum_score: float = 0.0,
        maximum_score: float = 1.0,
        county: str | None = None,
        top_n: int | None = None,
    ) -> dict[str, Any]:
        if minimum_score > maximum_score:
            raise ValueError(
                "minimum_score cannot exceed "
                "maximum_score."
            )

        frame = self.zones(
            mode
        ).copy()

        if "mean_score" in frame:
            score = pd.to_numeric(
                frame["mean_score"],
                errors="coerce",
            )

            mask = score.between(
                minimum_score,
                maximum_score,
                inclusive="both",
            )
        else:
            mask = pd.Series(
                True,
                index=frame.index,
            )

        if county:
            county_key = (
                county.strip().casefold()
            )

            county_columns = [
                column
                for column in (
                    "dominant_county",
                    "counties",
                )
                if column in frame
            ]

            county_mask = pd.Series(
                False,
                index=frame.index,
            )

            for column in county_columns:
                county_mask |= (
                    frame[column]
                    .astype(str)
                    .str.casefold()
                    .str.contains(
                        county_key,
                        regex=False,
                    )
                )

            mask &= county_mask

        filtered = frame.loc[
            mask
        ].copy()

        if (
            top_n is not None
            and top_n > 0
        ):
            sort_column = (
                "selection_rank"
                if "selection_rank"
                in filtered
                else "zone_rank_score"
            )

            ascending = (
                sort_column
                == "selection_rank"
            )

            filtered = (
                filtered.sort_values(
                    sort_column,
                    ascending=ascending,
                )
                .head(top_n)
            )

        return self._feature_collection(
            filtered,
            {
                "mode": mode,
                "minimum_score": (
                    minimum_score
                ),
                "maximum_score": (
                    maximum_score
                ),
                "county": county,
                "returned_count": (
                    len(filtered)
                ),
            },
        )

    def cell_detail(
        self,
        cell_id: str,
    ) -> dict[str, Any]:
        frame = self.final_grid()

        matches = frame.loc[
            frame["cell_id"].eq(
                str(cell_id)
            )
        ]

        if matches.empty:
            raise KeyError(cell_id)

        row = matches.iloc[0]

        def value(
            *names: str,
        ) -> Any:
            for name in names:
                if name in row.index:
                    return json_scalar(
                        row[name]
                    )

            return None

        exclusion_reasons = []

        if bool_value(
            value(
                "water_hard_excluded"
            )
        ):
            exclusion_reasons.append(
                "Mapped surface-water "
                "intersection"
            )

        if bool_value(
            value(
                "protected_hard_excluded"
            )
        ):
            exclusion_reasons.append(
                "Protected-land intersection"
            )

        if bool_value(
            value(
                "hydro_hazard_hard_excluded"
            )
        ):
            exclusion_reasons.append(
                "Inside or within configured "
                "SFHA buffer"
            )

        scores = {
            "climate": value(
                "climate_score"
            ),
            "grid_infrastructure": value(
                "grid_infrastructure_score"
            ),
            "telecom_infrastructure": value(
                "telecom_infrastructure_score"
            ),
            "protected_areas": value(
                "protected_areas_score"
            ),
            "water_bodies": value(
                "water_bodies_score"
            ),
            "population_density": value(
                "population_density_score"
            ),
            "road_access": value(
                "road_access_score"
            ),
            "hydro_hazard": value(
                "hydro_hazard_score"
            ),
        }

        return {
            "cell_id": str(
                row["cell_id"]
            ),
            "location": {
                "latitude": value(
                    "analysis_lat"
                ),
                "longitude": value(
                    "analysis_lon"
                ),
                "county_fips": value(
                    "county_fips"
                ),
                "county_name": value(
                    "county_name"
                ),
                "tract_geoid": value(
                    "GEOID"
                ),
                "land_fraction": value(
                    "land_fraction"
                ),
                "cell_area_sq_km": value(
                    "clipped_area_sq_km"
                ),
            },
            "decision": {
                "model_status": value(
                    "final_model_status"
                ),
                "hard_excluded": bool_value(
                    value(
                        "hard_excluded"
                    )
                ),
                "exclusion_reasons": (
                    exclusion_reasons
                ),
                "auto_screen_eligible": (
                    bool_value(
                        value(
                            "auto_screen_eligible"
                        )
                    )
                ),
                "exploration_screen_eligible": (
                    bool_value(
                        value(
                            "exploration_screen_eligible"
                        )
                    )
                ),
                "automated_recommendation_ready": (
                    bool_value(
                        value(
                            "automated_recommendation_ready"
                        )
                    )
                ),
            },
            "scores": {
                "technical_suitability": (
                    value(
                        "technical_suitability_score"
                    )
                ),
                "effective_suitability": (
                    value(
                        "effective_suitability_score"
                    )
                ),
                "criteria": scores,
            },
            "evidence": {
                "climate": {
                    "annual_mean_temperature_c": (
                        value(
                            "annual_mean_temperature_c"
                        )
                    ),
                    "july_mean_temperature_c": (
                        value(
                            "july_mean_temperature_c"
                        )
                    ),
                    "source_distance_m": value(
                        "climate_source_distance_m"
                    ),
                },
                "grid": {
                    "substation_distance_m": (
                        value(
                            "substation_distance_m"
                        )
                    ),
                    "transmission_distance_m": (
                        value(
                            "transmission_distance_m"
                        )
                    ),
                },
                "telecom": {
                    "fiber_distance_m": value(
                        "fiber_distance_m"
                    ),
                    "provider_count_5km": (
                        value(
                            "fiber_provider_count_5km"
                        )
                    ),
                    "source_quality": value(
                        "telecom_source_quality"
                    ),
                },
                "road": {
                    "major_road_distance_m": (
                        value(
                            "major_road_distance_m"
                        )
                    ),
                },
                "environment": {
                    "water_distance_m": value(
                        "water_distance_m"
                    ),
                    "protected_distance_m": (
                        value(
                            "protected_distance_m"
                        )
                    ),
                    "sfha_distance_m": value(
                        "sfha_distance_m"
                    ),
                    "sfha_buffer_m": value(
                        "sfha_buffer_m"
                    ),
                },
                "population": {
                    "population": value(
                        "population"
                    ),
                    "density_people_sq_km": (
                        value(
                            "population_density_people_sq_km"
                        )
                    ),
                },
            },
            "community_impact": {
                "equity_gate": value(
                    "equity_gate"
                ),
                "overburdened": value(
                    "overburdened"
                ),
                "underserved": value(
                    "underserved"
                ),
                "ej_percentile": value(
                    "ej_percentile"
                ),
                "pollution_burden_percentile": (
                    value(
                        "pollution_burden_percentile"
                    )
                ),
                "environmental_effects_percentile": (
                    value(
                        "environmental_effects_percentile"
                    )
                ),
                "sensitive_populations_percentile": (
                    value(
                        "sensitive_populations_percentile"
                    )
                ),
                "minority_or_hispanic_pct": (
                    value(
                        "minority_or_hispanic_pct"
                    )
                ),
                "low_income_pct": value(
                    "low_income_pct"
                ),
                "limited_english_pct": (
                    value(
                        "limited_english_pct"
                    )
                ),
                "used_in_technical_score": (
                    False
                ),
            },
        }

    def zone_detail(
        self,
        zone_id: str,
    ) -> dict[str, Any]:
        match = None
        matched_mode = None

        for mode in (
            "top",
            "auto",
            "exploration",
        ):
            frame = self.zones(
                mode
            )

            if "zone_id" not in frame:
                continue

            rows = frame.loc[
                frame["zone_id"]
                .astype(str)
                .eq(str(zone_id))
            ]

            if not rows.empty:
                match = rows.iloc[0]
                matched_mode = mode
                break

        if match is None:
            raise KeyError(zone_id)

        properties = {
            str(column): json_scalar(
                match[column]
            )
            for column in match.index
            if column != "geometry"
        }

        membership = self.membership()

        members = membership.loc[
            membership[
                "zone_id"
            ].astype(str).eq(
                str(zone_id)
            )
        ]

        member_ids = (
            members["cell_id"]
            .astype(str)
            .tolist()
        )

        final_grid = self.final_grid()

        member_frame = final_grid.loc[
            final_grid[
                "cell_id"
            ].isin(member_ids)
        ]

        score = pd.to_numeric(
            member_frame[
                "technical_suitability_score"
            ],
            errors="coerce",
        )

        return {
            "zone_id": str(zone_id),
            "mode": matched_mode,
            "properties": properties,
            "membership": {
                "member_count": (
                    len(member_ids)
                ),
                "member_cell_ids": (
                    member_ids[:2000]
                ),
                "member_cell_ids_truncated": (
                    len(member_ids) > 2000
                ),
            },
            "member_summary": {
                "technical_score": {
                    "minimum": (
                        json_scalar(
                            score.min()
                        )
                    ),
                    "median": (
                        json_scalar(
                            score.median()
                        )
                    ),
                    "mean": (
                        json_scalar(
                            score.mean()
                        )
                    ),
                    "maximum": (
                        json_scalar(
                            score.max()
                        )
                    ),
                },
                "equity_gate_counts": (
                    member_frame[
                        "equity_gate"
                    ]
                    .astype("string")
                    .fillna(
                        "INSUFFICIENT_DATA"
                    )
                    .value_counts()
                    .to_dict()
                ),
                "county_counts": (
                    member_frame[
                        "county_name"
                    ]
                    .astype("string")
                    .value_counts()
                    .to_dict()
                ),
            },
            "interpretation": (
                "Regional screening candidate "
                "zone. Parcel, zoning, utility, "
                "engineering, environmental, and "
                "community due diligence remain "
                "required."
            ),
        }

    def bias_audit(
        self,
    ) -> dict[str, Any]:
        return self._read_json(
            self.paths.bias_audit
        )

    def score_band_summary(
        self,
    ) -> dict[str, Any]:
        return self._read_json(
            self.paths.score_bands
        )
