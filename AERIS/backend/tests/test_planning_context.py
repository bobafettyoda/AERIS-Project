from __future__ import annotations

import unittest

from analysis.planning.planning_pipeline import (
    derive_planning_status,
    planning_confidence,
)


class PlanningContextTests(
    unittest.TestCase
):
    def test_missing_zoning_requires_manual_review(
        self,
    ) -> None:
        result = derive_planning_status(
            statewide_zoning=None,
            authority_status=(
                "COUNTY_PLANNING_"
                "REVIEW_REQUIRED"
            ),
            local_zoning_status=(
                "STATEWIDE_BASELINE_ONLY"
            ),
            active_development_status=(
                "SOURCE_DISCOVERY_REQUIRED"
            ),
            permits_status=(
                "SOURCE_DISCOVERY_REQUIRED"
            ),
        )

        self.assertEqual(
            result,
            (
                "STATEWIDE_ZONING_"
                "UNAVAILABLE_MANUAL_"
                "REVIEW_REQUIRED"
            ),
        )

    def test_municipality_takes_priority(
        self,
    ) -> None:
        result = derive_planning_status(
            statewide_zoning="R2",
            authority_status=(
                "MUNICIPAL_PLANNING_"
                "REVIEW_REQUIRED"
            ),
            local_zoning_status=(
                "STATEWIDE_BASELINE_ONLY"
            ),
            active_development_status=(
                "SOURCE_DISCOVERY_REQUIRED"
            ),
            permits_status=(
                "SOURCE_DISCOVERY_REQUIRED"
            ),
        )

        self.assertEqual(
            result,
            (
                "MUNICIPAL_AUTHORITY_"
                "VERIFICATION_REQUIRED"
            ),
        )

    def test_statewide_baseline_is_medium_confidence(
        self,
    ) -> None:
        result = planning_confidence(
            county_known=True,
            statewide_zoning_known=True,
            municipality_known=False,
            authoritative_local_zoning=False,
        )

        self.assertEqual(
            result,
            "MEDIUM",
        )


if __name__ == "__main__":
    unittest.main()
