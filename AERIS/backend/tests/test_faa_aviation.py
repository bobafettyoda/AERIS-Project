from __future__ import annotations

import unittest

from shapely.geometry import (
    LineString,
    Point,
)

from analysis.aviation.faa_nasr import (
    farthest_pair,
    physical_runway_polygon,
    runway_notice_distance_ft,
)


class FaaAviationTests(
    unittest.TestCase
):
    def test_long_runway_notice_distance(
        self,
    ) -> None:
        result = (
            runway_notice_distance_ft(
                longest_runway_ft=5000,
                long_runway_threshold_ft=3200,
                long_runway_distance_ft=20000,
                short_runway_distance_ft=10000,
            )
        )

        self.assertEqual(
            result,
            20000,
        )

    def test_short_runway_notice_distance(
        self,
    ) -> None:
        result = (
            runway_notice_distance_ft(
                longest_runway_ft=3200,
                long_runway_threshold_ft=3200,
                long_runway_distance_ft=20000,
                short_runway_distance_ft=10000,
            )
        )

        self.assertEqual(
            result,
            10000,
        )

    def test_physical_runway_area(
        self,
    ) -> None:
        centerline = LineString(
            [
                (0, 0),
                (1000, 0),
            ]
        )

        result = physical_runway_polygon(
            centerline=centerline,
            width_ft=100,
            feet_to_meters=0.3048,
            extra_buffer_m=0,
        )

        expected_area = (
            1000 * 30.48
        )

        self.assertAlmostEqual(
            result.area,
            expected_area,
            places=3,
        )

    def test_farthest_pair_ignores_duplicate_points(
        self,
    ) -> None:
        result = farthest_pair(
            [
                Point(0, 0),
                Point(0, 0),
                Point(10, 0),
                Point(4, 0),
            ]
        )

        self.assertIsNotNone(
            result
        )

        assert result is not None

        self.assertAlmostEqual(
            result[0].distance(
                result[1]
            ),
            10,
        )


if __name__ == "__main__":
    unittest.main()
