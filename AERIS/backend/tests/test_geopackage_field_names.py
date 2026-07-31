from __future__ import annotations

import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from analysis.statewide.environmental_constraints_pipeline import (
    normalize_geopackage_fields,
)


class GeoPackageFieldNameTests(
    unittest.TestCase
):
    def test_case_insensitive_collisions_are_renamed(
        self,
    ) -> None:
        attributes = pd.DataFrame(
            [
                [
                    "first",
                    "second",
                    "third",
                    42,
                ],
            ],
            columns=[
                "NAME",
                "Name",
                "name",
                "FID",
            ],
        )

        frame = gpd.GeoDataFrame(
            attributes,
            geometry=[
                Point(
                    -76.5,
                    39.0,
                )
            ],
            crs="EPSG:4326",
        )

        normalized = (
            normalize_geopackage_fields(
                frame
            )
        )

        folded_names = [
            str(column).casefold()
            for column in (
                normalized.columns
            )
        ]

        self.assertEqual(
            len(folded_names),
            len(set(folded_names)),
        )

        self.assertNotIn(
            "fid",
            folded_names,
        )

        self.assertEqual(
            normalized.iloc[0, 0],
            "first",
        )

        self.assertEqual(
            normalized.iloc[0, 1],
            "second",
        )

        self.assertEqual(
            normalized.iloc[0, 2],
            "third",
        )

        self.assertEqual(
            normalized.iloc[0, 3],
            42,
        )


if __name__ == "__main__":
    unittest.main()
