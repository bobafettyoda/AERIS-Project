from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.release import runtime_release_metadata


class RuntimeReleaseMetadataTests(unittest.TestCase):
    def test_runtime_release_metadata_reads_deployment_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AERIS_DEPLOYMENT_RELEASE_ID": "aeris-v0.8.0-test",
                "AERIS_DATA_SNAPSHOT_ID": "baseline-test",
                "AERIS_DATA_MANIFEST_SHA256": "abc123",
            },
            clear=False,
        ):
            self.assertEqual(
                runtime_release_metadata(),
                {
                    "deployment_release_id": "aeris-v0.8.0-test",
                    "data_snapshot_id": "baseline-test",
                    "data_manifest_sha256": "abc123",
                },
            )

    def test_runtime_release_metadata_uses_none_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                runtime_release_metadata(),
                {
                    "deployment_release_id": None,
                    "data_snapshot_id": None,
                    "data_manifest_sha256": None,
                },
            )


if __name__ == "__main__":
    unittest.main()
