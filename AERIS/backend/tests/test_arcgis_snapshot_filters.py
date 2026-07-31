from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from analysis.statewide.grid_infrastructure_pipeline import (
    object_ids_in_envelope,
)


class ArcGISSnapshotFilterTests(
    unittest.TestCase
):
    @patch(
        "analysis.statewide."
        "grid_infrastructure_pipeline."
        "request_json"
    )
    def test_spatial_filter_is_forwarded(
        self,
        request_json: Mock,
    ) -> None:
        request_json.return_value = {
            "objectIds": [
                3,
                1,
                2,
            ],
        }

        result = object_ids_in_envelope(
            session=Mock(),
            layer_url=(
                "https://example.test/"
                "FeatureServer/0"
            ),
            envelope={
                "xmin": -77.0,
                "ymin": 38.0,
                "xmax": -76.0,
                "ymax": 39.0,
            },
            where="SFHA_TF = 'T'",
        )

        self.assertEqual(
            result,
            [
                1,
                2,
                3,
            ],
        )

        data = (
            request_json.call_args
            .kwargs["data"]
        )

        self.assertEqual(
            data["where"],
            "SFHA_TF = 'T'",
        )

        self.assertIn(
            "geometry",
            data,
        )

    @patch(
        "analysis.statewide."
        "grid_infrastructure_pipeline."
        "request_json"
    )
    def test_attribute_only_query_omits_geometry(
        self,
        request_json: Mock,
    ) -> None:
        request_json.return_value = {
            "objectIds": [
                30,
                10,
                20,
            ],
        }

        result = object_ids_in_envelope(
            session=Mock(),
            layer_url=(
                "https://example.test/"
                "FeatureServer/1"
            ),
            envelope=None,
            where="SFHA_TF = 'T'",
        )

        self.assertEqual(
            result,
            [
                10,
                20,
                30,
            ],
        )

        data = (
            request_json.call_args
            .kwargs["data"]
        )

        self.assertEqual(
            data["where"],
            "SFHA_TF = 'T'",
        )

        self.assertNotIn(
            "geometry",
            data,
        )

        self.assertEqual(
            data["returnIdsOnly"],
            "true",
        )


if __name__ == "__main__":
    unittest.main()
