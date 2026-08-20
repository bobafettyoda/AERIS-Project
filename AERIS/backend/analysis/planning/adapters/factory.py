from __future__ import annotations

from analysis.planning.adapters.base import PlanningAdapter
from analysis.planning.adapters.null_adapter import NullPlanningAdapter
from analysis.planning.models import JurisdictionRecord


class UnsupportedPlanningAdapterError(RuntimeError):
    pass


def adapter_for_jurisdiction(
    record: JurisdictionRecord,
) -> PlanningAdapter:
    configured = {
        value
        for value in (
            record.zoning.adapter,
            record.active_development.adapter,
            record.permits.adapter,
        )
        if value
    }

    if not configured or configured == {"null"}:
        return NullPlanningAdapter()

    raise UnsupportedPlanningAdapterError(
        f"Unsupported planning adapter(s) for {record.name}: "
        + ", ".join(sorted(configured))
    )
