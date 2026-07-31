from __future__ import annotations

import unittest

from analysis.statewide.grid_infrastructure_pipeline import (
    selected_fields,
)


class ArcGISMetadataHelperTests(
    unittest.TestCase
):
    def test_top_level_object_id_field(
        self,
    ) -> None:
        metadata = {
            "objectIdField": "FID",
            "fields": [
                {
                    "name": "FID",
                    "type": (
                        "esriFieldTypeOID"
                    ),
                },
                {
                    "name": "NAME",
                    "type": (
                        "esriFieldTypeString"
                    ),
                },
            ],
        }

        object_id, fields = (
            selected_fields(
                metadata,
                ["NAME"],
            )
        )

        self.assertEqual(
            object_id,
            "FID",
        )

        self.assertEqual(
            fields,
            [
                "FID",
                "NAME",
            ],
        )

    def test_oid_field_type_fallback(
        self,
    ) -> None:
        metadata = {
            "fields": [
                {
                    "name": "OBJECTID",
                    "type": (
                        "esriFieldTypeOID"
                    ),
                },
                {
                    "name": "ROADNAMESHA",
                    "type": (
                        "esriFieldTypeString"
                    ),
                },
                {
                    "name": "ID_PREFIX",
                    "type": (
                        "esriFieldTypeString"
                    ),
                },
            ],
        }

        object_id, fields = (
            selected_fields(
                metadata,
                [
                    "ROADNAMESHA",
                    "ID_PREFIX",
                    "MISSING_FIELD",
                ],
            )
        )

        self.assertEqual(
            object_id,
            "OBJECTID",
        )

        self.assertEqual(
            fields,
            [
                "OBJECTID",
                "ROADNAMESHA",
                "ID_PREFIX",
            ],
        )


if __name__ == "__main__":
    unittest.main()
