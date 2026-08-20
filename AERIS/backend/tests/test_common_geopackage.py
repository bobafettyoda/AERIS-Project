from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from analysis.common.geopackage import (
    read_single_row,
    write_geopackage_atomic,
)


class CommonGeoPackageTests(unittest.TestCase):
    def test_atomic_write_and_indexed_single_row_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.gpkg"
            frame = gpd.GeoDataFrame(
                {
                    "parcel_id": ["A", "B"],
                    "score": [0.7, 0.9],
                },
                geometry=[Point(0, 0), Point(1, 1)],
                crs="EPSG:4326",
            )
            written = write_geopackage_atomic(
                path=path,
                layers=[("parcels", frame)],
                indexes=[("parcels", "parcel_id")],
            )
            self.assertEqual(written, ["parcels"])
            row = read_single_row(
                path,
                layer="parcels",
                key_column="parcel_id",
                key_value="B",
                read_geometry=False,
            )
            self.assertEqual(row["parcel_id"], "B")
            self.assertAlmostEqual(float(row["score"]), 0.9)

    def test_single_row_read_escapes_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.gpkg"
            frame = gpd.GeoDataFrame(
                {"parcel_id": ["O'Brien"]},
                geometry=[Point(0, 0)],
                crs="EPSG:4326",
            )
            write_geopackage_atomic(
                path=path,
                layers=[("parcels", frame)],
            )
            row = read_single_row(
                path,
                layer="parcels",
                key_column="parcel_id",
                key_value="O'Brien",
            )
            self.assertEqual(row["parcel_id"], "O'Brien")


if __name__ == "__main__":
    unittest.main()
