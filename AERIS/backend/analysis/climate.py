from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import yaml

from analysis.decision_model import DecisionModel


NASA_POWER_CLIMATOLOGY_URL = (
    "https://power.larc.nasa.gov/api/"
    "temporal/climatology/point"
)


class ClimateCriterion:
    """Evaluate climate as a regional cooling-burden proxy."""

    def __init__(self) -> None:
        self.criterion_name = "climate"
        self.source_layer = (
            "NASA POWER point climatology"
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

        scoring = model_config.get("climate_scoring")

        if not scoring:
            raise RuntimeError(
                "climate_scoring is missing from the "
                "decision-model YAML."
            )

        self.method = scoring["method"]

        self.annual_component_weight = float(
            scoring[
                "annual_temperature_component_weight"
            ]
        )
        self.july_component_weight = float(
            scoring[
                "july_temperature_component_weight"
            ]
        )

        component_total = (
            self.annual_component_weight
            + self.july_component_weight
        )

        if abs(component_total - 1.0) > 0.000001:
            raise RuntimeError(
                "Climate component weights must total 1.0."
            )

        self.annual_points = self._load_points(
            scoring["annual_mean_temperature_points"]
        )

        self.july_points = self._load_points(
            scoring["july_mean_temperature_points"]
        )

        self.limitations = list(
            scoring.get("limitations", [])
        )

    @staticmethod
    def _load_points(
        raw_points: list[dict[str, Any]],
    ) -> list[tuple[float, float]]:
        points = [
            (
                float(point["temperature_c"]),
                float(point["score"]),
            )
            for point in raw_points
        ]

        points.sort(key=lambda point: point[0])

        if len(points) < 2:
            raise RuntimeError(
                "Climate scoring requires at least "
                "two temperature points."
            )

        return points

    @staticmethod
    def _interpolate_score(
        value: float,
        points: list[tuple[float, float]],
    ) -> float:
        first_value, first_score = points[0]

        if value <= first_value:
            return round(first_score, 6)

        for index in range(1, len(points)):
            lower_value, lower_score = points[
                index - 1
            ]
            upper_value, upper_score = points[index]

            if value <= upper_value:
                interval = upper_value - lower_value

                if interval == 0:
                    return round(upper_score, 6)

                fraction = (
                    value - lower_value
                ) / interval

                score = lower_score + fraction * (
                    upper_score - lower_score
                )

                return round(
                    max(0.0, min(1.0, score)),
                    6,
                )

        return round(points[-1][1], 6)

    @staticmethod
    def _valid_number(
        value: Any,
        parameter_name: str,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"NASA POWER did not return a valid "
                f"value for {parameter_name}."
            ) from error

        if number == -999.0:
            raise RuntimeError(
                f"NASA POWER returned its fill value "
                f"for {parameter_name}."
            )

        return number

    @staticmethod
    def _request_climatology(
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        response = requests.get(
            NASA_POWER_CLIMATOLOGY_URL,
            params={
                "parameters": (
                    "T2M,T2M_MAX,T2M_MIN,RH2M"
                ),
                "community": "RE",
                "longitude": lon,
                "latitude": lat,
                "format": "JSON",
            },
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            raise RuntimeError(
                "NASA POWER returned an error: "
                f"{payload['error']}"
            )

        return payload

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        payload = self._request_climatology(
            lat=lat,
            lon=lon,
        )

        parameters = (
            payload.get("properties", {})
            .get("parameter", {})
        )

        required_parameters = (
            "T2M",
            "T2M_MAX",
            "T2M_MIN",
            "RH2M",
        )

        missing = [
            parameter
            for parameter in required_parameters
            if parameter not in parameters
        ]

        if missing:
            raise RuntimeError(
                "NASA POWER response is missing: "
                + ", ".join(missing)
            )

        annual_mean_c = self._valid_number(
            parameters["T2M"].get("ANN"),
            "T2M ANN",
        )

        july_mean_c = self._valid_number(
            parameters["T2M"].get("JUL"),
            "T2M JUL",
        )

        annual_humidity_pct = self._valid_number(
            parameters["RH2M"].get("ANN"),
            "RH2M ANN",
        )

        july_humidity_pct = self._valid_number(
            parameters["RH2M"].get("JUL"),
            "RH2M JUL",
        )

        extreme_max_c = self._valid_number(
            parameters["T2M_MAX"].get("ANN"),
            "T2M_MAX ANN",
        )

        extreme_min_c = self._valid_number(
            parameters["T2M_MIN"].get("ANN"),
            "T2M_MIN ANN",
        )

        annual_score = self._interpolate_score(
            annual_mean_c,
            self.annual_points,
        )

        july_score = self._interpolate_score(
            july_mean_c,
            self.july_points,
        )

        normalized_score = round(
            (
                annual_score
                * self.annual_component_weight
            )
            + (
                july_score
                * self.july_component_weight
            ),
            6,
        )

        contribution = self.model.contribution(
            self.criterion_name,
            normalized_score,
        )

        header = payload.get("header", {})
        geometry = payload.get("geometry", {})

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "methodology": self.method,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "source_coordinate": {
                "coordinates": geometry.get(
                    "coordinates"
                ),
            },
            "climatology_period": header.get("range"),
            "source_products": header.get("sources"),
            "temperature_c": {
                "annual_mean": round(
                    annual_mean_c,
                    2,
                ),
                "july_mean": round(
                    july_mean_c,
                    2,
                ),
                "climatological_extreme_max": round(
                    extreme_max_c,
                    2,
                ),
                "climatological_extreme_min": round(
                    extreme_min_c,
                    2,
                ),
            },
            "relative_humidity_pct": {
                "annual_mean": round(
                    annual_humidity_pct,
                    2,
                ),
                "july_mean": round(
                    july_humidity_pct,
                    2,
                ),
                "included_in_score": False,
            },
            "component_scores": {
                "annual_mean_temperature": {
                    "value_c": round(
                        annual_mean_c,
                        2,
                    ),
                    "score": annual_score,
                    "component_weight": (
                        self.annual_component_weight
                    ),
                },
                "july_mean_temperature": {
                    "value_c": round(
                        july_mean_c,
                        2,
                    ),
                    "score": july_score,
                    "component_weight": (
                        self.july_component_weight
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
