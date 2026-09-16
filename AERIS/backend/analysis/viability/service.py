from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import pyogrio

from analysis.common.io import load_yaml
from analysis.parcels.grid_feasibility_api_service import ParcelGridFeasibilityService
from analysis.planning.planning_api_service import PlanningContextService
from analysis.site_feasibility.api_service import SiteFeasibilityService
from analysis.statewide.api_service import StatewideDataService
from analysis.viability.engine import evaluate_scope_records


class ViabilityService:
    def __init__(
        self,
        *,
        config_path: Path,
        statewide_service: StatewideDataService,
        site_service: SiteFeasibilityService,
        grid_service: ParcelGridFeasibilityService,
        planning_service: PlanningContextService,
    ) -> None:
        self.config_path = config_path.resolve()
        self.config = load_yaml(self.config_path)
        self.statewide_service = statewide_service
        self.site_service = site_service
        self.grid_service = grid_service
        self.planning_service = planning_service

    def methodology(self) -> dict[str, Any]:
        return deepcopy(self.config)

    @staticmethod
    def _scope_id(zone_id: str) -> str:
        cleaned = "-".join(
            part
            for part in "".join(
                char.lower() if char.isalnum() else " "
                for char in str(zone_id)
            ).split()
            if part
        )
        return f"zone-{cleaned}"

    def _artifact_readiness(self, scope_id: str) -> dict[str, bool]:
        site_paths = self.site_service._paths(scope_id)
        grid_paths = self.grid_service._paths(scope_id)
        planning_output, planning_manifest = self.planning_service._paths(scope_id)
        return {
            "site": site_paths.output.exists() and site_paths.manifest.exists(),
            "grid": grid_paths.output.exists() and grid_paths.manifest.exists(),
            "planning": planning_output.exists() and planning_manifest.exists(),
        }

    def search_areas(
        self,
        *,
        mode: str | None = None,
        minimum_score: float | None = None,
        maximum_score: float | None = None,
        county: str | None = None,
    ) -> dict[str, Any]:
        search = self.config["search_areas"]
        mode = mode or str(search["default_mode"])
        if mode not in set(search["allowed_modes"]):
            raise ValueError(f"Unsupported search-area mode: {mode}")

        payload = self.statewide_service.zone_feature_collection(
            mode=mode,  # type: ignore[arg-type]
            minimum_score=(
                float(search["minimum_regional_score"])
                if minimum_score is None
                else minimum_score
            ),
            maximum_score=(
                float(search["maximum_regional_score"])
                if maximum_score is None
                else maximum_score
            ),
            county=county,
            top_n=None,
        )

        state_counts: dict[str, int] = {}
        for feature in payload.get("features", []):
            props = feature.setdefault("properties", {})
            zone_id = str(props.get("zone_id") or "")
            scope_id = self._scope_id(zone_id)
            readiness = self._artifact_readiness(scope_id)
            props["scope_id"] = scope_id
            props["analysis_role"] = "REGIONAL_SEARCH_AREA"
            props["fixed_rank_shortlist"] = False
            if all(readiness.values()):
                try:
                    result = self.evaluate_scope(scope_id=scope_id, include_all=False)
                    state = str(result["scope_status"])
                    props["comparison_eligible_count"] = result["counts"][
                        "comparison_eligible"
                    ]
                except Exception:
                    state = "EVIDENCE_READY_EVALUATION_ERROR"
            elif any(readiness.values()):
                state = "PARTIAL_EVIDENCE"
            else:
                state = "NOT_INVESTIGATED"
            props["viability_state"] = state
            state_counts[state] = state_counts.get(state, 0) + 1

        metadata = payload.setdefault("metadata", {})
        metadata.update(
            {
                "terminology": "regional_search_area",
                "fixed_top_n": False,
                "viability_state_counts": state_counts,
                "next_stage": (
                    "Build parcel/site evidence for a search area, then evaluate "
                    "configured viability gates before comparison."
                ),
            }
        )
        return payload

    @staticmethod
    def _read_table(path: Path, layer: str) -> pd.DataFrame:
        if not path.exists():
            raise KeyError(str(path))
        return pyogrio.read_dataframe(path, layer=layer, read_geometry=False)

    def _scope_records(self, scope_id: str) -> list[dict[str, Any]]:
        readiness = self._artifact_readiness(scope_id)
        missing = [name for name, ready in readiness.items() if not ready]
        if missing:
            raise KeyError(
                f"Scope {scope_id!r} is missing viability evidence: {', '.join(missing)}"
            )

        site_paths = self.site_service._paths(scope_id)
        site = self._read_table(
            site_paths.output,
            self.site_service.config["layers"]["parcel_analysis"],
        )

        grid_paths = self.grid_service._paths(scope_id)
        grid = self._read_table(
            grid_paths.output,
            self.grid_service.config["layers"]["parcel_analysis"],
        )

        planning_output, _ = self.planning_service._paths(scope_id)
        planning = self._read_table(
            planning_output,
            self.planning_service.config["layers"]["parcel_analysis"],
        )

        grid_columns = [
            column
            for column in (
                "parcel_id",
                "public_grid_context_class",
                "grid_data_confidence",
                "capacity_status",
                "utility_confirmation_required",
                "interconnection_study_required",
                "statewide_grid_infrastructure_score",
            )
            if column in grid.columns
        ]
        planning_columns = [
            column
            for column in (
                "parcel_id",
                "planning_review_status",
                "planning_data_confidence",
                "manual_local_verification_required",
                "local_zoning_verified",
                "permitted_use_determined",
            )
            if column in planning.columns
        ]

        merged = site.merge(
            grid[grid_columns].drop_duplicates("parcel_id"),
            on="parcel_id",
            how="left",
            validate="one_to_one",
            suffixes=("", "_grid"),
        ).merge(
            planning[planning_columns].drop_duplicates("parcel_id"),
            on="parcel_id",
            how="left",
            validate="one_to_one",
            suffixes=("", "_planning"),
        )

        return merged.to_dict(orient="records")

    def evaluate_scope(
        self,
        *,
        scope_id: str,
        include_all: bool = False,
    ) -> dict[str, Any]:
        readiness = self._artifact_readiness(scope_id)
        if not all(readiness.values()):
            missing = [name for name, ready in readiness.items() if not ready]
            return {
                "scope_id": scope_id,
                "scope_status": "NOT_READY",
                "artifact_readiness": readiness,
                "missing_artifacts": missing,
                "counts": {
                    "evaluated": 0,
                    "comparison_eligible": 0,
                    "evidence_hold": 0,
                    "rejected": 0,
                },
                "rejection_reason_counts": {},
                "hold_reason_counts": {},
                "review_reason_counts": {},
                "comparison_candidates": [],
                "evaluated_candidates": [],
                "safeguards": deepcopy(self.config["safeguards"]),
            }

        result = evaluate_scope_records(self._scope_records(scope_id), self.config)
        result["scope_id"] = scope_id
        result["artifact_readiness"] = readiness
        result["missing_artifacts"] = []
        result["safeguards"] = deepcopy(self.config["safeguards"])
        result["interpretation"] = {
            "comparison_eligible_means": (
                "Passes configured AERIS screening gates and may advance to "
                "comparative due diligence."
            ),
            "comparison_eligible_does_not_mean": (
                "Development-ready, utility-capacity-confirmed, entitled, "
                "acquisition-controlled, or permit-approved."
            ),
        }
        if not include_all:
            result.pop("evaluated_candidates", None)
        return result

    def compare_candidates(
        self,
        *,
        scope_id: str,
        candidate_ids: list[str],
    ) -> list[dict[str, Any]]:
        evaluation = self.evaluate_scope(scope_id=scope_id, include_all=False)
        candidates = evaluation.get("comparison_candidates", [])
        lookup = {str(item["candidate_id"]): item for item in candidates}
        missing = [value for value in candidate_ids if str(value) not in lookup]
        if missing:
            raise KeyError(
                "Candidates are not comparison-eligible or were not found: "
                + ", ".join(missing)
            )
        return [lookup[str(value)] for value in candidate_ids]
