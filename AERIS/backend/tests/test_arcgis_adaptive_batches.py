from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from requests.exceptions import RetryError

from analysis.statewide.grid_infrastructure_pipeline import (
    query_feature_batch,
)


def feature(
    object_id: int,
) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": object_id,
        },
        "geometry": {
            "type": "Point",
            "coordinates": [
                -76.5,
                39.0,
            ],
        },
    }


class ArcGISAdaptiveBatchTests(
    unittest.TestCase
):
    @patch(
        "analysis.statewide."
        "grid_infrastructure_pipeline."
        "request_json"
    )
    def test_failed_batch_is_split(
        self,
        request_json: Mock,
    ) -> None:
        request_json.side_effect = [
            RetryError(
                "simulated server 500"
            ),
            {
                "type": (
                    "FeatureCollection"
                ),
                "features": [
                    feature(1),
                    feature(2),
                ],
            },
            {
                "type": (
                    "FeatureCollection"
                ),
                "features": [
                    feature(3),
                    feature(4),
                ],
            },
        ]

        result = query_feature_batch(
            session=Mock(),
            layer_url=(
                "https://example.test/"
                "FeatureServer/1"
            ),
            object_ids=[
                1,
                2,
                3,
                4,
            ],
            output_fields=[
                "OBJECTID",
            ],
            name="sfha",
        )

        self.assertEqual(
            len(result),
            4,
        )

        self.assertEqual(
            request_json.call_count,
            3,
        )

        self.assertEqual(
            [
                item["properties"][
                    "OBJECTID"
                ]
                for item in result
            ],
            [
                1,
                2,
                3,
                4,
            ],
        )


if __name__ == "__main__":
    unittest.main()
