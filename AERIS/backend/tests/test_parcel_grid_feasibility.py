from __future__ import annotations

import unittest

from analysis.parcels.grid_feasibility_pipeline import (
    derive_grid_context_class,
    voltage_class,
)


VOLTAGE_CONFIG = {
    "extra_high_minimum_kv": 345,
    "high_minimum_kv": 230,
    "regional_minimum_kv": 115,
    "subtransmission_minimum_kv": 69,
}


CONTEXT_CONFIG = {
    "very_strong": {
        "transmission_distance_m": 2000,
        "transmission_voltage_kv": 230,
        "substation_distance_m": 7500,
        "substation_voltage_kv": 115,
    },
    "strong": {
        "transmission_distance_m": 5000,
        "transmission_voltage_kv": 115,
        "substation_distance_m": 12000,
    },
    "moderate": {
        "transmission_distance_m": 10000,
        "substation_distance_m": 15000,
    },
}


class ParcelGridFeasibilityTests(
    unittest.TestCase
):
    def test_voltage_classes(
        self,
    ) -> None:
        self.assertEqual(
            voltage_class(
                500,
                VOLTAGE_CONFIG,
            ),
            "EXTRA_HIGH_345_KV_PLUS",
        )

        self.assertEqual(
            voltage_class(
                230,
                VOLTAGE_CONFIG,
            ),
            "HIGH_230_TO_344_KV",
        )

        self.assertEqual(
            voltage_class(
                115,
                VOLTAGE_CONFIG,
            ),
            "REGIONAL_115_TO_229_KV",
        )

        self.assertEqual(
            voltage_class(
                69,
                VOLTAGE_CONFIG,
            ),
            "SUBTRANSMISSION_69_TO_114_KV",
        )

        self.assertEqual(
            voltage_class(
                None,
                VOLTAGE_CONFIG,
            ),
            "UNKNOWN",
        )

    def test_very_strong_context(
        self,
    ) -> None:
        result = (
            derive_grid_context_class(
                transmission_distance_m=1000,
                transmission_voltage_kv=230,
                substation_distance_m=4000,
                substation_voltage_kv=230,
                maximum_nearby_voltage_kv=345,
                context_config=(
                    CONTEXT_CONFIG
                ),
            )
        )

        self.assertEqual(
            result,
            (
                "VERY_STRONG_MAPPED_"
                "GRID_CONTEXT"
            ),
        )

    def test_moderate_context_with_unknown_voltage(
        self,
    ) -> None:
        result = (
            derive_grid_context_class(
                transmission_distance_m=8000,
                transmission_voltage_kv=None,
                substation_distance_m=14000,
                substation_voltage_kv=None,
                maximum_nearby_voltage_kv=None,
                context_config=(
                    CONTEXT_CONFIG
                ),
            )
        )

        self.assertEqual(
            result,
            (
                "MODERATE_MAPPED_"
                "GRID_CONTEXT"
            ),
        )

    def test_missing_context(
        self,
    ) -> None:
        result = (
            derive_grid_context_class(
                transmission_distance_m=None,
                transmission_voltage_kv=None,
                substation_distance_m=None,
                substation_voltage_kv=None,
                maximum_nearby_voltage_kv=None,
                context_config=(
                    CONTEXT_CONFIG
                ),
            )
        )

        self.assertEqual(
            result,
            (
                "INSUFFICIENT_MAPPED_"
                "GRID_DATA"
            ),
        )


if __name__ == "__main__":
    unittest.main()
