from __future__ import annotations

import json
from typing import Any

import requests


class MarylandStudyArea:
    """Validate candidate points against Maryland's boundary."""

    def __init__(self, layer_url: str) -> None:
        self.layer_url = layer_url.rstrip("/")
        self.name = "Maryland"

    @staticmethod
    def _raise_for_arcgis_error(
        payload: dict[str, Any],
    ) -> None:
        if "error" not in payload:
            return

        error = payload["error"]

        raise RuntimeError(
            "Maryland boundary service error: "
            f"{error.get('code')} - "
            f"{error.get('message')}"
        )

    def evaluate(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
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
                "where": "State = 'Maryland'",
                "geometry": json.dumps(geometry),
                "geometryType": (
                    "esriGeometryPoint"
                ),
                "inSR": "4326",
                "spatialRel": (
                    "esriSpatialRelIntersects"
                ),
                "returnCountOnly": "true",
            },
            headers={
                "User-Agent": "AERIS/0.1",
            },
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()
        self._raise_for_arcgis_error(payload)

        count = int(payload.get("count", 0))

        return {
            "name": self.name,
            "inside_study_area": count > 0,
            "matched_boundary_count": count,
            "input": {
                "lat": lat,
                "lon": lon,
            },
        }

    def boundary_geojson(
        self,
    ) -> dict[str, Any]:
        response = requests.post(
            f"{self.layer_url}/query",
            data={
                "f": "geojson",
                "where": "State = 'Maryland'",
                "outFields": "State",
                "returnGeometry": "true",
                "outSR": "4326",
            },
            headers={
                "User-Agent": "AERIS/0.1",
            },
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()
        self._raise_for_arcgis_error(payload)

        return payload
