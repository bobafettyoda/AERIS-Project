from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import Polygon

from analysis.statewide.grid_infrastructure_pipeline import (
    repair_invalid_geometries,
)


class GeometryRepairTests(
    unittest.TestCase
):
    def test_invalid_polygon_is_repaired(
        self,
    ) -> None:
        bow_tie = Polygon(
            [
                (0.0, 0.0),
                (1.0, 1.0),
                (1.0, 0.0),
                (0.0, 1.0),
                (0.0, 0.0),
            ]
        )

        self.assertFalse(
            bow_tie.is_valid
        )

        frame = gpd.GeoDataFrame(
            {
                "OBJECTID": [1],
            },
            geometry=[bow_tie],
            crs="EPSG:4326",
        )

        repaired = (
            repair_invalid_geometries(
                frame,
                name="test",
            )
        )

        self.assertEqual(
            len(repaired),
            1,
        )

        self.assertTrue(
            repaired.geometry.iloc[0].is_valid
        )

        self.assertFalse(
            repaired.geometry.iloc[0].is_empty
        )


if __name__ == "__main__":
    unittest.main()
