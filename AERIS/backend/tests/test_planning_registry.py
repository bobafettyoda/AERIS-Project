from __future__ import annotations

import unittest
from pathlib import Path

from analysis.planning.registry import (
    PlanningRegistry,
)


PROJECT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
)


class PlanningRegistryTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.registry = (
            PlanningRegistry(
                PROJECT_DIRECTORY
                / "configs"
                / "planning"
                / "maryland_jurisdictions.yaml"
            )
        )

    def test_registry_contains_all_24_jurisdictions(
        self,
    ) -> None:
        self.assertEqual(
            len(
                self.registry.records
            ),
            24,
        )

    def test_county_authority(
        self,
    ) -> None:
        result = (
            self.registry
            .resolve_authority(
                county_fips="027",
                municipality_name=None,
            )
        )

        self.assertEqual(
            result.authority_status,
            (
                "COUNTY_PLANNING_"
                "REVIEW_REQUIRED"
            ),
        )

    def test_regular_municipality(
        self,
    ) -> None:
        result = (
            self.registry
            .resolve_authority(
                county_fips="003",
                municipality_name=(
                    "Annapolis"
                ),
            )
        )

        self.assertEqual(
            result.authority_status,
            (
                "COUNTY_AND_MUNICIPAL_AUTHORITY_"
                "VERIFICATION_REQUIRED"
            ),
        )

    def test_independent_montgomery_municipality(
        self,
    ) -> None:
        result = (
            self.registry
            .resolve_authority(
                county_fips="031",
                municipality_name=(
                    "Rockville"
                ),
            )
        )

        self.assertEqual(
            result.authority_status,
            (
                "INDEPENDENT_MUNICIPAL_"
                "PLANNING_REVIEW_REQUIRED"
            ),
        )

    def test_non_independent_division_two_municipality(
        self,
    ) -> None:
        result = (
            self.registry
            .resolve_authority(
                county_fips="033",
                municipality_name=(
                    "College Park"
                ),
            )
        )

        self.assertEqual(
            result.authority_status,
            (
                "COUNTY_OR_BI_COUNTY_"
                "PLANNING_REVIEW_REQUIRED"
            ),
        )


if __name__ == "__main__":
    unittest.main()
