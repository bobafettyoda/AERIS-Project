from __future__ import annotations

import json
from typing import Any

import requests


class EquityScreen:
    """
    Evaluate Maryland environmental-justice
    indicators separately from technical suitability.
    """

    FIELDS = (
        "GEOID20,"
        "P_EJ,"
        "OVERBURDENED,"
        "OVERBURDENED_SUM,"
        "UNDERSERVED,"
        "P_UNDERSERVED,"
        "P_POLLUTIONBURDEN,"
        "P_POLLUTIONENVIRONMENTAL,"
        "P_SENSITIVEPOPULATIONS,"
        "MINORPCT,"
        "LWINCPCT,"
        "LINGISOPCT"
    )

    def __init__(self, layer_url: str) -> None:
        self.layer_url = layer_url.rstrip("/")
        self.source_layer = (
            "Maryland EJ Score V3"
        )

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:
        if value in (None, ""):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _percent(
        cls,
        value: Any,
    ) -> float | None:
        number = cls._number(value)

        if number is None:
            return None

        if 0 <= number <= 1:
            return round(number * 100, 2)

        return round(number, 2)

    def _query(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any] | None:
        geometry = {
            "x": lon,
            "y": lat,
            "spatialReference": {
                "wkid": 4326,
            },
        }

        response = requests.post(
            f"{self.layer_url}/query",
            data={
                "f": "json",
                "where": "1=1",
                "geometry": json.dumps(geometry),
                "geometryType": (
                    "esriGeometryPoint"
                ),
                "inSR": "4326",
                "spatialRel": (
                    "esriSpatialRelIntersects"
                ),
                "outFields": self.FIELDS,
                "returnGeometry": "false",
            },
            headers={
                "User-Agent": "AERIS/0.1",
            },
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]

            raise RuntimeError(
                "MDEnviroScreen service error: "
                f"{error.get('code')} - "
                f"{error.get('message')}"
            )

        features = payload.get("features", [])

        if not features:
            return None

        return features[0].get(
            "attributes",
            {},
        )

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        attributes = self._query(
            lat=lat,
            lon=lon,
        )

        if not attributes:
            return {
                "source_layer": self.source_layer,
                "input": {
                    "lat": lat,
                    "lon": lon,
                },
                "gate_status": (
                    "INSUFFICIENT_DATA"
                ),
                "auto_recommendation_eligible": (
                    False
                ),
                "used_in_suitability_score": False,
                "message": (
                    "No MDEnviroScreen tract "
                    "was returned for this point."
                ),
            }

        ej_percentile = self._percent(
            attributes.get("P_EJ")
        )

        pollution_burden_percentile = (
            self._percent(
                attributes.get(
                    "P_POLLUTIONBURDEN"
                )
            )
        )

        environmental_effects_percentile = (
            self._percent(
                attributes.get(
                    "P_POLLUTIONENVIRONMENTAL"
                )
            )
        )

        sensitive_populations_percentile = (
            self._percent(
                attributes.get(
                    "P_SENSITIVEPOPULATIONS"
                )
            )
        )

        underserved_percentile = self._percent(
            attributes.get("P_UNDERSERVED")
        )

        minority_pct = self._percent(
            attributes.get("MINORPCT")
        )

        low_income_pct = self._percent(
            attributes.get("LWINCPCT")
        )

        limited_english_pct = self._percent(
            attributes.get("LINGISOPCT")
        )

        overburdened_factor_count = (
            self._number(
                attributes.get(
                    "OVERBURDENED_SUM"
                )
            )
        )

        overburdened = (
            overburdened_factor_count
            is not None
            and overburdened_factor_count >= 3
        )

        underserved_reasons: list[str] = []

        if (
            low_income_pct is not None
            and low_income_pct >= 25
        ):
            underserved_reasons.append(
                "low_income"
            )

        if (
            minority_pct is not None
            and minority_pct >= 50
        ):
            underserved_reasons.append(
                "minority_or_hispanic_population"
            )

        if (
            limited_english_pct is not None
            and limited_english_pct >= 15
        ):
            underserved_reasons.append(
                "limited_english_proficiency"
            )

        underserved = bool(
            underserved_reasons
        )

        elevated_categories = []

        category_values = {
            "ej_score": ej_percentile,
            "pollution_burden": (
                pollution_burden_percentile
            ),
            "environmental_effects": (
                environmental_effects_percentile
            ),
            "sensitive_populations": (
                sensitive_populations_percentile
            ),
            "underserved": (
                underserved_percentile
            ),
        }

        for name, value in (
            category_values.items()
        ):
            if (
                value is not None
                and value >= 75
            ):
                elevated_categories.append(name)

        if overburdened:
            gate_status = "HIGH_BURDEN"
        elif (
            underserved
            or elevated_categories
        ):
            gate_status = "CAUTION"
        else:
            gate_status = "PASS"

        return {
            "source_layer": self.source_layer,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "tract_geoid": attributes.get(
                "GEOID20"
            ),
            "gate_status": gate_status,
            "auto_recommendation_eligible": (
                gate_status == "PASS"
            ),
            "used_in_suitability_score": False,
            "demographic_fields_are_audit_only": (
                True
            ),
            "overburdened": overburdened,
            "overburdened_factor_count": (
                overburdened_factor_count
            ),
            "underserved": underserved,
            "underserved_reasons": (
                underserved_reasons
            ),
            "elevated_categories": (
                elevated_categories
            ),
            "percentiles": {
                "environmental_justice": (
                    ej_percentile
                ),
                "pollution_burden": (
                    pollution_burden_percentile
                ),
                "environmental_effects": (
                    environmental_effects_percentile
                ),
                "sensitive_populations": (
                    sensitive_populations_percentile
                ),
                "underserved": (
                    underserved_percentile
                ),
            },
            "demographic_audit": {
                "minority_or_hispanic_pct": (
                    minority_pct
                ),
                "low_income_pct": (
                    low_income_pct
                ),
                "limited_english_pct": (
                    limited_english_pct
                ),
            },
            "interpretation": {
                "PASS": (
                    "No elevated equity gate "
                    "condition was detected."
                ),
                "CAUTION": (
                    "Enhanced community-impact "
                    "review is required."
                ),
                "HIGH_BURDEN": (
                    "The location cannot be "
                    "automatically recommended."
                ),
                "INSUFFICIENT_DATA": (
                    "A recommendation cannot be "
                    "issued without additional data."
                ),
            }.get(gate_status),
        }
