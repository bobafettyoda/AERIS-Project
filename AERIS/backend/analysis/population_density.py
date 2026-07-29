from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import yaml

from analysis.decision_model import DecisionModel


CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/"
    "geographies/coordinates"
)

ACS_BASE_URL = "https://api.census.gov/data"


class PopulationDensityCriterion:
    def __init__(self) -> None:
        self.criterion_name = "population_density"
        self.source_layer = (
            "U.S. Census Bureau Geocoder and ACS 5-year estimates"
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

        scoring = model_config.get("population_density_scoring")

        if not scoring:
            raise RuntimeError(
                "population_density_scoring is missing from "
                "data_center_maryland_demo.yaml"
            )

        self.method = scoring["method"]
        self.acs_year = int(scoring["acs_year"])
        self.units = scoring["units"]

        self.score_points = [
            (
                float(point["density"]),
                float(point["score"]),
            )
            for point in scoring["points"]
        ]

        self.score_points.sort(key=lambda point: point[0])

    @staticmethod
    def _api_key() -> str:
        api_key = os.getenv("CENSUS_API_KEY", "").strip()

        if not api_key:
            raise RuntimeError(
                "CENSUS_API_KEY is not set in this terminal."
            )

        return api_key

    def _find_tract(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        response = requests.get(
            CENSUS_GEOCODER_URL,
            params={
                "x": lon,
                "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()
        geographies = (
            payload.get("result", {})
            .get("geographies", {})
        )

        tract_records: list[dict[str, Any]] = []

        for geography_name, records in geographies.items():
            if "tract" in geography_name.lower():
                tract_records.extend(records)

        if not tract_records:
            raise RuntimeError(
                "The Census geocoder did not return a census tract."
            )

        tract = tract_records[0]

        required_fields = [
            "GEOID",
            "STATE",
            "COUNTY",
            "TRACT",
            "AREALAND",
        ]

        missing = [
            field
            for field in required_fields
            if not tract.get(field)
        ]

        if missing:
            raise RuntimeError(
                "Census tract is missing required fields: "
                + ", ".join(missing)
            )

        return tract

    def _get_population(
        self,
        state: str,
        county: str,
        tract: str,
    ) -> dict[str, Any]:
        response = requests.get(
            f"{ACS_BASE_URL}/{self.acs_year}/acs/acs5",
            params=[
                ("get", "NAME,B01003_001E"),
                ("for", f"tract:{tract}"),
                ("in", f"state:{state} county:{county}"),
                ("key", self._api_key()),
            ],
            headers={"User-Agent": "AERIS/0.1"},
            timeout=60,
            allow_redirects=False,
        )

        if 300 <= response.status_code < 400:
            raise RuntimeError(
                "The Census API redirected the request. "
                "Check whether CENSUS_API_KEY is valid."
            )

        response.raise_for_status()

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "json" not in content_type:
            raise RuntimeError(
                "The Census API returned a non-JSON response."
            )

        rows = response.json()

        if not isinstance(rows, list) or len(rows) < 2:
            raise RuntimeError(
                "The ACS did not return population data "
                "for this census tract."
            )

        headers = rows[0]
        values = rows[1]
        record = dict(zip(headers, values, strict=False))

        population_value = record.get("B01003_001E")

        if population_value in (None, "", "-666666666"):
            raise RuntimeError(
                "The ACS population estimate is unavailable "
                "for this census tract."
            )

        return {
            "name": record.get("NAME"),
            "population": int(population_value),
        }

    def _normalize_density(
        self,
        density: float,
    ) -> float:
        first_density, first_score = self.score_points[0]

        if density <= first_density:
            return round(first_score, 6)

        for index in range(1, len(self.score_points)):
            lower_density, lower_score = (
                self.score_points[index - 1]
            )
            upper_density, upper_score = (
                self.score_points[index]
            )

            if density <= upper_density:
                interval = upper_density - lower_density

                if interval == 0:
                    return round(upper_score, 6)

                fraction = (
                    density - lower_density
                ) / interval

                score = lower_score + fraction * (
                    upper_score - lower_score
                )

                return round(
                    max(0.0, min(1.0, score)),
                    6,
                )

        return round(self.score_points[-1][1], 6)

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        tract = self._find_tract(
            lat=lat,
            lon=lon,
        )

        acs = self._get_population(
            state=str(tract["STATE"]),
            county=str(tract["COUNTY"]),
            tract=str(tract["TRACT"]),
        )

        land_area_sq_m = float(tract["AREALAND"])
        land_area_sq_km = land_area_sq_m / 1_000_000

        if land_area_sq_km <= 0:
            raise RuntimeError(
                "The census tract has no valid land area."
            )

        population = acs["population"]
        density = population / land_area_sq_km
        score = self._normalize_density(density)

        contribution = self.model.contribution(
            self.criterion_name,
            score,
        )

        return {
            "criterion": self.criterion_name,
            "source_layer": self.source_layer,
            "methodology": self.method,
            "input": {
                "lat": lat,
                "lon": lon,
            },
            "acs_year": self.acs_year,
            "tract": {
                "name": acs["name"],
                "geoid": tract["GEOID"],
                "state_fips": tract["STATE"],
                "county_fips": tract["COUNTY"],
                "tract_code": tract["TRACT"],
            },
            "population": population,
            "land_area_sq_m": round(
                land_area_sq_m,
                2,
            ),
            "land_area_sq_km": round(
                land_area_sq_km,
                6,
            ),
            "density_people_sq_km": round(
                density,
                2,
            ),
            "excluded": False,
            "normalized_score": score,
            "weight": contribution["weight"],
            "weighted_contribution": contribution[
                "weighted_contribution"
            ],
            "limitations": [
                (
                    "This version uses only the census tract "
                    "containing the candidate point."
                ),
                (
                    "Neighboring-tract workforce access is not "
                    "yet included."
                ),
                (
                    "The scoring curve is provisional and can "
                    "be adjusted in the decision-model YAML."
                ),
            ],
        }
