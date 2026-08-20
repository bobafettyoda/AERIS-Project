from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import geopandas as gpd

from analysis.planning.models import (
    AdapterEvidence,
)


@dataclass(frozen=True)
class AdapterScope:
    county_fips: str
    authority_name: str
    geometry: Any
    target_crs: str


class PlanningAdapter(ABC):
    adapter_name: str

    @abstractmethod
    def available(
        self,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def zoning(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        raise NotImplementedError

    @abstractmethod
    def active_development(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        raise NotImplementedError

    @abstractmethod
    def permits(
        self,
        *,
        parcels: gpd.GeoDataFrame,
        scope: AdapterScope,
    ) -> dict[str, AdapterEvidence]:
        raise NotImplementedError
