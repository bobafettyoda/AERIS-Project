from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.transform import from_origin
from shapely.geometry import box

from analysis.site_feasibility.raster import (
    choose_pixel_size,
    compute_slope_percent,
    threshold_polygons,
    tile_bounds,
    zonal_raster_statistics,
)


class SiteFeasibilityRasterTests(unittest.TestCase):
    def test_pixel_size_respects_total_pixel_budget(self) -> None:
        value = choose_pixel_size(
            (0, 0, 10000, 10000),
            target_pixel_size_m=1,
            maximum_pixel_size_m=30,
            maximum_total_pixels=1_000_000,
        )
        self.assertAlmostEqual(value, 10.0)

    def test_pixel_budget_rejects_scope_that_is_too_large(self) -> None:
        with self.assertRaisesRegex(ValueError, "smaller parcel scope"):
            choose_pixel_size(
                (0, 0, 200000, 200000),
                target_pixel_size_m=10,
                maximum_pixel_size_m=30,
                maximum_total_pixels=1_000_000,
            )

    def test_tile_bounds_cover_scope(self) -> None:
        tiles = tile_bounds(
            (0, 0, 100, 80),
            pixel_size_m=10,
            maximum_tile_pixels=5,
        )
        self.assertEqual(len(tiles), 4)
        self.assertEqual(tiles[0], (0, 0, 50, 50))
        self.assertEqual(tiles[-1], (50, 50, 100, 80))

    def test_slope_percent_for_planar_surface(self) -> None:
        # One meter rise per ten meters run = 10 percent slope.
        x = np.arange(5, dtype=float)
        dem = np.tile(x, (5, 1))
        slope = compute_slope_percent(
            dem,
            transform=Affine(10, 0, 0, 0, -10, 50),
            nodata=None,
        )
        self.assertTrue(np.allclose(slope, 10.0))

    def test_zonal_stats_and_threshold_polygons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slope.tif"
            data = np.array(
                [
                    [0, 0, 20, 20],
                    [0, 0, 20, 20],
                    [0, 0, 20, 20],
                    [0, 0, 20, 20],
                ],
                dtype="float32",
            )
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=4,
                width=4,
                count=1,
                dtype="float32",
                crs="EPSG:26985",
                transform=from_origin(0, 40, 10, 10),
            ) as dataset:
                dataset.write(data, 1)

            statistics = zonal_raster_statistics(
                geometries=[box(0, 0, 40, 40)],
                raster_path=path,
                thresholds=(15,),
            )[0]
            self.assertEqual(statistics["count"], 16)
            self.assertAlmostEqual(statistics["mean"], 10.0)
            self.assertAlmostEqual(statistics["fraction_ge_15"], 0.5)

            polygons = threshold_polygons(
                raster_path=path,
                threshold=15,
                minimum_area_sq_m=1,
            )
            self.assertEqual(len(polygons), 1)
            self.assertAlmostEqual(polygons.geometry.iloc[0].area, 800.0)


if __name__ == "__main__":
    unittest.main()
