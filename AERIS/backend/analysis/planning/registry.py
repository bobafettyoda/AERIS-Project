from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from analysis.planning.models import (
    JurisdictionRecord,
    PlanningAuthorityResolution,
    SourceStatus,
)


VALID_SOURCE_STATUSES = {
    "AVAILABLE",
    "STATEWIDE_BASELINE_ONLY",
    "PARTIAL",
    "SOURCE_DISCOVERY_REQUIRED",
    "MANUAL_REVIEW_REQUIRED",
    "DATA_UNAVAILABLE",
    "ERROR",
}


def load_registry_yaml(
    path: Path,
) -> dict[str, Any]:
    value = yaml.safe_load(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(value, dict):
        raise RuntimeError(
            f"Expected registry object: {path}"
        )

    return value


def merge_source_config(
    default: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    result = deepcopy(default)

    if override:
        result.update(override)

    return result


def source_status(
    value: dict[str, Any],
) -> SourceStatus:
    status = str(
        value.get(
            "status",
            "ERROR",
        )
    ).strip().upper()

    if status not in VALID_SOURCE_STATUSES:
        raise RuntimeError(
            f"Invalid planning-source status: {status}"
        )

    return SourceStatus(
        status=status,
        adapter=(
            None
            if value.get("adapter") in (
                None,
                "",
            )
            else str(
                value["adapter"]
            )
        ),
        endpoint=(
            None
            if value.get("endpoint") in (
                None,
                "",
            )
            else str(
                value["endpoint"]
            )
        ),
        note=str(
            value.get(
                "note",
                "",
            )
        ),
        authoritative_local_geometry=bool(
            value.get(
                "authoritative_local_geometry",
                False,
            )
        ),
    )


class PlanningRegistry:
    def __init__(
        self,
        registry_path: Path,
    ) -> None:
        self.registry_path = (
            registry_path.resolve()
        )

        payload = load_registry_yaml(
            self.registry_path
        )

        self.payload = payload

        defaults = payload[
            "default_local_sources"
        ]

        jurisdictions = payload[
            "jurisdictions"
        ]

        self.records: dict[
            str,
            JurisdictionRecord,
        ] = {}

        for raw_fips, raw_record in (
            jurisdictions.items()
        ):
            county_fips = str(
                raw_fips
            ).zfill(3)

            local_sources = (
                raw_record.get(
                    "local_sources",
                    {},
                )
            )

            zoning = source_status(
                merge_source_config(
                    defaults["zoning"],
                    local_sources.get(
                        "zoning"
                    ),
                )
            )

            comprehensive = (
                source_status(
                    merge_source_config(
                        defaults[
                            "comprehensive_plan"
                        ],
                        local_sources.get(
                            "comprehensive_plan"
                        ),
                    )
                )
            )

            active = source_status(
                merge_source_config(
                    defaults[
                        "active_development"
                    ],
                    local_sources.get(
                        "active_development"
                    ),
                )
            )

            permits = source_status(
                merge_source_config(
                    defaults["permits"],
                    local_sources.get(
                        "permits"
                    ),
                )
            )

            self.records[
                county_fips
            ] = JurisdictionRecord(
                county_fips=county_fips,
                name=str(
                    raw_record["name"]
                ),
                jurisdiction_code=str(
                    raw_record[
                        "jurisdiction_code"
                    ]
                ),
                authority_profile=str(
                    raw_record[
                        "authority_profile"
                    ]
                ),
                independent_municipalities=tuple(
                    str(value)
                    for value
                    in raw_record.get(
                        "independent_municipalities",
                        [],
                    )
                ),
                zoning=zoning,
                comprehensive_plan=(
                    comprehensive
                ),
                active_development=(
                    active
                ),
                permits=permits,
            )

        expected = int(
            payload[
                "expected_jurisdiction_count"
            ]
        )

        if len(self.records) != expected:
            raise RuntimeError(
                f"Expected {expected} jurisdictions; "
                f"found {len(self.records)}."
            )

    def get(
        self,
        county_fips: str,
    ) -> JurisdictionRecord:
        normalized = str(
            county_fips
        ).zfill(3)

        try:
            return self.records[
                normalized
            ]
        except KeyError as error:
            raise KeyError(
                f"Unknown Maryland county FIPS: "
                f"{normalized}"
            ) from error

    def resolve_authority(
        self,
        *,
        county_fips: str,
        municipality_name: str | None,
    ) -> PlanningAuthorityResolution:
        record = self.get(
            county_fips
        )

        municipality = (
            municipality_name.strip()
            if municipality_name
            and municipality_name.strip()
            else None
        )

        if record.authority_profile == (
            "BALTIMORE_CITY"
        ):
            return PlanningAuthorityResolution(
                county_fips=record.county_fips,
                county_name=record.name,
                municipality_name=None,
                authority_profile=(
                    record.authority_profile
                ),
                authority_level="CITY",
                authority_name="Baltimore City",
                authority_status=(
                    "CITY_PLANNING_REVIEW_REQUIRED"
                ),
                manual_local_verification_required=True,
            )

        if municipality is None:
            authority_status = (
                "COUNTY_OR_BI_COUNTY_"
                "PLANNING_REVIEW_REQUIRED"
                if record.authority_profile
                == "DIVISION_II_MNCPPC"
                else "COUNTY_PLANNING_REVIEW_REQUIRED"
            )

            return PlanningAuthorityResolution(
                county_fips=record.county_fips,
                county_name=record.name,
                municipality_name=None,
                authority_profile=(
                    record.authority_profile
                ),
                authority_level="COUNTY",
                authority_name=record.name,
                authority_status=(
                    authority_status
                ),
                manual_local_verification_required=True,
            )

        independent_lookup = {
            value.casefold(): value
            for value
            in record.independent_municipalities
        }

        if record.authority_profile == (
            "DIVISION_II_MNCPPC"
        ):
            if (
                municipality.casefold()
                in independent_lookup
            ):
                authority_name = (
                    independent_lookup[
                        municipality.casefold()
                    ]
                )

                return PlanningAuthorityResolution(
                    county_fips=record.county_fips,
                    county_name=record.name,
                    municipality_name=municipality,
                    authority_profile=(
                        record.authority_profile
                    ),
                    authority_level="MUNICIPALITY",
                    authority_name=authority_name,
                    authority_status=(
                        "INDEPENDENT_MUNICIPAL_"
                        "PLANNING_REVIEW_REQUIRED"
                    ),
                    manual_local_verification_required=True,
                )

            return PlanningAuthorityResolution(
                county_fips=record.county_fips,
                county_name=record.name,
                municipality_name=municipality,
                authority_profile=(
                    record.authority_profile
                ),
                authority_level="COUNTY_OR_BI_COUNTY",
                authority_name=record.name,
                authority_status=(
                    "COUNTY_OR_BI_COUNTY_"
                    "PLANNING_REVIEW_REQUIRED"
                ),
                manual_local_verification_required=True,
            )

        # A mapped municipal boundary does not, by itself, establish which
        # zoning/planning powers that municipality exercises. Keep both the
        # county and municipality visible until an authoritative authority
        # matrix or local adapter verifies the governing role.
        return PlanningAuthorityResolution(
            county_fips=record.county_fips,
            county_name=record.name,
            municipality_name=municipality,
            authority_profile=record.authority_profile,
            authority_level="COUNTY_AND_MUNICIPALITY",
            authority_name=f"{record.name} / {municipality}",
            authority_status=(
                "COUNTY_AND_MUNICIPAL_AUTHORITY_"
                "VERIFICATION_REQUIRED"
            ),
            manual_local_verification_required=True,
        )

    def coverage_summary(
        self,
    ) -> dict[str, Any]:
        return {
            "jurisdiction_count": (
                len(self.records)
            ),
            "county_fips": sorted(
                self.records
            ),
            "source_status_counts": {
                source_name: {
                    status: sum(
                        1
                        for record
                        in self.records.values()
                        if getattr(
                            record,
                            source_name,
                        ).status
                        == status
                    )
                    for status
                    in sorted(
                        VALID_SOURCE_STATUSES
                    )
                }
                for source_name in (
                    "zoning",
                    "comprehensive_plan",
                    "active_development",
                    "permits",
                )
            },
        }
