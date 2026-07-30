from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import yaml

from analysis.decision_model import DecisionModel


FIBER_COVERAGE_QUERY_URL = (
    "https://mdgeodata.md.gov/imap/rest/services/"
    "UtilityTelecom/MD_BroadbandServiceAreas/"
    "MapServer/3/query"
)


class TelecomInfrastructureCriterion:
    """Evaluate public indications of nearby fiber availability."""

    def __init__(self) -> None:
        self.criterion_name = "telecom_infrastructure"
        self.source_layer = (
            "Maryland iMAP Fiber Optic Provider Coverage"
        )

        self.model = DecisionModel()

        model_path = (
            Path(__file__).resolve().parents[2]
            / "configs"
            / "decision_models"
            / "data_center_maryland_demo.yaml"
        )

        with model_path.open("r", encoding="utf-8") as file:
            model_config = yaml.safe_load(file)

        scoring = model_config.get(
            "telecom_infrastructure_scoring"
        )

        if not scoring:
            raise RuntimeError(
                "telecom_infrastructure_scoring is missing "
                "from the decision-model YAML."
            )

        self.method = scoring["method"]

        self.proximity_component_weight = float(
            scoring["proximity_component_weight"]
        )
        self.diversity_component_weight = float(
            scoring["diversity_component_weight"]
        )

        component_total = (
            self.proximity_component_weight
            + self.diversity_component_weight
        )

        if abs(component_total - 1.0) > 0.000001:
            raise RuntimeError(
                "Telecom component weights must total 1.0."
            )

        self.diversity_search_radius_m = int(
            scoring["diversity_search_radius_m"]
        )

        self.proximity_scores = {
            key: float(value)
            for key, value in scoring[
                "proximity_scores"
            ].items()
        }

        self.diversity_scores = {
            key: float(value)
            for key, value in scoring[
                "provider_diversity_scores"
            ].items()
        }

        self.limitations = list(
            scoring.get("limitations", [])
        )

    @staticmethod
    def _point_parameters(
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        return {
            "where": "TRANSTECH = 50",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
        }

    @staticmethod
    def _request(
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        response = requests.get(
            FIBER_COVERAGE_QUERY_URL,
            params=parameters,
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            raise RuntimeError(
                "Maryland fiber service returned an error: "
                f"{error}"
            )

        return payload

    def _coverage_count(
        self,
        lat: float,
        lon: float,
        distance_m: int | None,
    ) -> int:
        parameters = self._point_parameters(
            lat=lat,
            lon=lon,
        )

        parameters["returnCountOnly"] = "true"

        if distance_m is not None:
            parameters["distance"] = distance_m
            parameters["units"] = "esriSRUnit_Meter"

        payload = self._request(parameters)

        return int(payload.get("count", 0))

    def _coverage_object_ids(
        self,
        lat: float,
        lon: float,
        distance_m: int,
    ) -> list[int]:
        parameters = self._point_parameters(
            lat=lat,
            lon=lon,
        )

        parameters.update(
            {
                "distance": distance_m,
                "units": "esriSRUnit_Meter",
                "returnIdsOnly": "true",
            }
        )

        payload = self._request(parameters)

        return [
            int(object_id)
            for object_id in (
                payload.get("objectIds") or []
            )
        ]

    def _provider_records(
        self,
        object_ids: list[int],
    ) -> list[dict[str, Any]]:
        if not object_ids:
            return []

        records: list[dict[str, Any]] = []

        for start in range(0, len(object_ids), 500):
            chunk = object_ids[start : start + 500]

            payload = self._request(
                {
                    "objectIds": ",".join(
                        str(object_id)
                        for object_id in chunk
                    ),
                    "outFields": (
                        "PROVNAME,DBANAME,FRN,TRANSTECH,"
                        "MAXADDOWN,MAXADUP,TYPICDOWN,"
                        "TYPICUP,EndUserCat"
                    ),
                    "returnGeometry": "false",
                    "f": "json",
                }
            )

            for feature in payload.get(
                "features",
                [],
            ):
                records.append(
                    feature.get("attributes", {})
                )

        return records

    @staticmethod
    def _distinct_providers(
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        providers: dict[str, dict[str, Any]] = {}

        for record in records:
            frn = str(
                record.get("FRN") or ""
            ).strip()

            dba_name = str(
                record.get("DBANAME") or ""
            ).strip()

            provider_name = str(
                record.get("PROVNAME") or ""
            ).strip()

            provider_key = (
                frn
                or dba_name
                or provider_name
            )

            if not provider_key:
                continue

            if provider_key not in providers:
                providers[provider_key] = {
                    "provider_name": (
                        dba_name
                        or provider_name
                    ),
                    "parent_provider_name": (
                        provider_name or None
                    ),
                    "frn": frn or None,
                    "coverage_record_count": 0,
                    "maximum_download_codes": set(),
                    "maximum_upload_codes": set(),
                }

            provider = providers[provider_key]
            provider["coverage_record_count"] += 1

            download_code = record.get("MAXADDOWN")
            upload_code = record.get("MAXADUP")

            if download_code not in (None, ""):
                provider[
                    "maximum_download_codes"
                ].add(str(download_code))

            if upload_code not in (None, ""):
                provider[
                    "maximum_upload_codes"
                ].add(str(upload_code))

        results: list[dict[str, Any]] = []

        for provider in providers.values():
            provider[
                "maximum_download_codes"
            ] = sorted(
                provider[
                    "maximum_download_codes"
                ]
            )

            provider[
                "maximum_upload_codes"
            ] = sorted(
                provider[
                    "maximum_upload_codes"
                ]
            )

            results.append(provider)

        results.sort(
            key=lambda provider: (
                provider["provider_name"] or ""
            ).lower()
        )

        return results

    def _proximity_result(
        self,
        counts: dict[int, int],
        direct_count: int,
    ) -> tuple[str, int | None, float]:
        if direct_count > 0:
            return (
                "direct_coverage",
                0,
                self.proximity_scores[
                    "direct_coverage"
                ],
            )

        bands = [
            (
                500,
                "within_500_m",
            ),
            (
                1000,
                "within_1000_m",
            ),
            (
                2000,
                "within_2000_m",
            ),
            (
                5000,
                "within_5000_m",
            ),
        ]

        for distance_m, score_key in bands:
            if counts.get(distance_m, 0) > 0:
                return (
                    score_key,
                    distance_m,
                    self.proximity_scores[
                        score_key
                    ],
                )

        return (
            "beyond_5000_m",
            None,
            self.proximity_scores[
                "beyond_5000_m"
            ],
        )

    def _diversity_score(
        self,
        provider_count: int,
    ) -> float:
        if provider_count <= 0:
            key = "zero_providers"
        elif provider_count == 1:
            key = "one_provider"
        elif provider_count == 2:
            key = "two_providers"
        elif provider_count == 3:
            key = "three_providers"
        else:
            key = "four_or_more_providers"

        return self.diversity_scores[key]

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        search_distances = (
            500,
            1000,
            2000,
            self.diversity_search_radius_m,
        )

        direct_count = self._coverage_count(
            lat=lat,
            lon=lon,
            distance_m=None,
        )

        counts = {
            distance_m: self._coverage_count(
                lat=lat,
                lon=lon,
                distance_m=distance_m,
            )
            for distance_m in search_distances
        }

        proximity_band, nearest_band_m, (
            proximity_score
        ) = self._proximity_result(
            counts=counts,
            direct_count=direct_count,
        )

        object_ids = self._coverage_object_ids(
            lat=lat,
            lon=lon,
            distance_m=(
                self.diversity_search_radius_m
            ),
        )

        records = self._provider_records(
            object_ids
        )

        providers = self._distinct_providers(
            records
        )

        provider_count = len(providers)

        diversity_score = self._diversity_score(
            provider_count
        )

        normalized_score = round(
            (
                proximity_score
                * self.proximity_component_weight
            )
            + (
                diversity_score
                * self.diversity_component_weight
            ),
            6,
        )

        contribution = self.model.contribution(
            self.criterion_name,
            normalized_score,
        )

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "methodology": self.method,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "direct_reported_coverage": (
                direct_count > 0
            ),
            "direct_coverage_record_count": (
                direct_count
            ),
            "nearest_reported_coverage_band": (
                proximity_band
            ),
            "nearest_reported_coverage_m": (
                nearest_band_m
            ),
            "coverage_record_counts": {
                f"within_{distance_m}_m": (
                    counts[distance_m]
                )
                for distance_m in search_distances
            },
            "provider_search_radius_m": (
                self.diversity_search_radius_m
            ),
            "distinct_provider_count": (
                provider_count
            ),
            "providers": providers,
            "component_scores": {
                "proximity": {
                    "score": proximity_score,
                    "component_weight": (
                        self.proximity_component_weight
                    ),
                },
                "provider_diversity": {
                    "score": diversity_score,
                    "component_weight": (
                        self.diversity_component_weight
                    ),
                },
            },
            "excluded": False,
            "normalized_score": normalized_score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
            "limitations": self.limitations,
        }
