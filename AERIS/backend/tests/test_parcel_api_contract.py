from __future__ import annotations

import unittest

from analysis.common.geojson import (
    feature_collection as common_feature_collection,
)
from analysis.parcels import api_service as parcel_api_service
from app.main import app


class ParcelApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.openapi = app.openapi()

    def test_builds_use_post_and_reads_use_get(self) -> None:
        paths = self.openapi["paths"]
        self.assertIn(
            "post",
            paths["/analysis/parcels/build/zone/{zone_id}"],
        )
        self.assertIn(
            "get",
            paths["/analysis/parcels/jobs/{job_id}"],
        )
        self.assertIn(
            "get",
            paths["/analysis/parcels/scopes/{scope_id}/bundle"],
        )

    def test_read_only_artifact_routes_do_not_expose_refresh(self) -> None:
        for path in (
            "/analysis/parcels/scopes/{scope_id}/development-envelopes",
            "/analysis/parcels/scopes/{scope_id}/constraints",
            "/analysis/parcels/scopes/{scope_id}/grid-evidence",
            "/analysis/parcels/scopes/{scope_id}/planning-evidence",
        ):
            parameters = self.openapi["paths"][path]["get"].get(
                "parameters",
                [],
            )
            self.assertNotIn(
                "refresh",
                {parameter["name"] for parameter in parameters},
            )

    def test_parcel_service_has_shared_geojson_builder(
        self,
    ) -> None:
        self.assertIs(
            parcel_api_service.feature_collection,
            common_feature_collection,
        )

    def test_parcel_detail_has_response_schema(self) -> None:
        operation = self.openapi["paths"][
            "/analysis/parcels/scopes/{scope_id}/parcels/{parcel_id}"
        ]["get"]
        schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        self.assertEqual(
            schema["$ref"],
            "#/components/schemas/ParcelDetailResponse",
        )


if __name__ == "__main__":
    unittest.main()
