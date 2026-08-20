from __future__ import annotations

import geopandas as gpd


def repair_invalid_geometries(
    frame: gpd.GeoDataFrame,
    *,
    name: str,
) -> gpd.GeoDataFrame:
    repaired = frame.loc[frame.geometry.notna()].copy()
    repaired = repaired.loc[~repaired.geometry.is_empty].copy()

    invalid_mask = ~repaired.geometry.is_valid
    invalid_count = int(invalid_mask.sum())

    if invalid_count:
        print(
            f"      [{name}] repairing {invalid_count:,} invalid geometries",
            flush=True,
        )
        try:
            fixed = repaired.loc[invalid_mask].geometry.make_valid()
        except AttributeError:
            from shapely import make_valid

            fixed = repaired.loc[invalid_mask].geometry.map(make_valid)

        repaired.loc[invalid_mask, "geometry"] = fixed
        repaired = repaired.loc[
            repaired.geometry.notna() & ~repaired.geometry.is_empty
        ].copy()

    remaining = int((~repaired.geometry.is_valid).sum())
    if remaining:
        raise RuntimeError(
            f"{name}: {remaining:,} geometries remain invalid after repair."
        )

    return repaired
