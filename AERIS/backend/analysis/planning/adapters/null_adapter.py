from __future__ import annotations

import geopandas as gpd

from analysis.planning.adapters.base import (
    AdapterScope,
    PlanningAdapter,
)
from analysis.planning.models import (
    AdapterEvidence,
)


class NullPlanningAdapter(
    PlanningAdapter
):
    adapter_name = "null"

    def available(
        self,
    ) -> bool:
        return False

    @staticmethod
    def _result(
        parcels: gpd.GeoDataFrame,
        category: str,
    ) -> dict[str, AdapterEvidence]:
        return {
            str(parcel_id): AdapterEvidence(
                status=(
                    "MANUAL_REVIEW_REQUIRED"
                ),
                source_name=None,
                source_url=None,
                source_date=None,
                attributes={},
                warning=(
                    f"No automated local "
                    f"{category} adapter is "
                    "configured. Absence of "
                    "automated evidence does not "
                    "mean no restriction or "
                    "activity exists."
                ),
            )
            for parcel_id
            in parcels[
                "parcel_id"
            ].astype(str)
        }

    def zoning(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        return self._result(
            parcels,
            "zoning",
        )

    def active_development(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        return self._result(
            parcels,
            "active-development",
        )

    def permits(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        return self._result(
            parcels,
            "permit",
        )
