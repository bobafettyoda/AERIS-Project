from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceStatus:
    status: str
    adapter: str | None
    endpoint: str | None
    note: str
    authoritative_local_geometry: bool = False


@dataclass(frozen=True)
class JurisdictionRecord:
    county_fips: str
    name: str
    jurisdiction_code: str
    authority_profile: str
    independent_municipalities: tuple[str, ...]
    zoning: SourceStatus
    comprehensive_plan: SourceStatus
    active_development: SourceStatus
    permits: SourceStatus


@dataclass(frozen=True)
class PlanningAuthorityResolution:
    county_fips: str
    county_name: str
    municipality_name: str | None
    authority_profile: str
    authority_level: str
    authority_name: str
    authority_status: str
    manual_local_verification_required: bool


@dataclass(frozen=True)
class AdapterEvidence:
    status: str
    source_name: str | None
    source_url: str | None
    source_date: str | None
    attributes: dict[str, Any]
    warning: str | None
