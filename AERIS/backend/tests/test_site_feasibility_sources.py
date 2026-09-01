from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analysis.common.io import atomic_write_json
from analysis.site_feasibility.sources import (
    _cache_is_current,
)


class SiteFeasibilitySourceTests(
    unittest.TestCase
):
    def test_empty_snapshot_metadata_is_cacheable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "snapshot.json"
            snapshot = root / "snapshot.gpkg"

            atomic_write_json(
                metadata,
                {
                    "fingerprint": "abc",
                    "empty": True,
                },
            )

            self.assertTrue(
                _cache_is_current(
                    metadata_path=metadata,
                    snapshot_path=snapshot,
                    fingerprint="abc",
                )
            )

    def test_nonempty_cache_requires_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "snapshot.json"
            snapshot = root / "snapshot.gpkg"

            atomic_write_json(
                metadata,
                {
                    "fingerprint": "abc",
                    "empty": False,
                },
            )

            self.assertFalse(
                _cache_is_current(
                    metadata_path=metadata,
                    snapshot_path=snapshot,
                    fingerprint="abc",
                )
            )


if __name__ == "__main__":
    unittest.main()
