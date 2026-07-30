from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analysis.statewide.acquisition import (
    chunked,
    parse_acs_response,
    sha256_file,
)


class StatewideAcquisitionTests(
    unittest.TestCase
):
    def test_chunked_preserves_values(
        self,
    ) -> None:
        result = list(
            chunked(
                [1, 2, 3, 4, 5],
                2,
            )
        )

        self.assertEqual(
            result,
            [
                [1, 2],
                [3, 4],
                [5],
            ],
        )

    def test_parse_acs_response_builds_geoid(
        self,
    ) -> None:
        rows = [
            [
                "NAME",
                "B01003_001E",
                "B01003_001M",
                "state",
                "county",
                "tract",
            ],
            [
                "Test tract",
                "1000",
                "75",
                "24",
                "033",
                "980000",
            ],
        ]

        frame = parse_acs_response(
            rows=rows,
            variables={
                "NAME": "tract_name",
                "B01003_001E": (
                    "population"
                ),
                "B01003_001M": (
                    "population_moe"
                ),
            },
        )

        self.assertEqual(
            frame.iloc[0]["GEOID"],
            "24033980000",
        )

        self.assertEqual(
            frame.iloc[0][
                "population"
            ],
            1000,
        )

    def test_sha256_file_is_stable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "sample.txt"
            )

            path.write_text(
                "AERIS",
                encoding="utf-8",
            )

            first = sha256_file(path)
            second = sha256_file(path)

            self.assertEqual(
                first,
                second,
            )

            self.assertEqual(
                len(first),
                64,
            )


if __name__ == "__main__":
    unittest.main()
