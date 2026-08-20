from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

import geopandas as gpd
import pandas as pd
import pyogrio


def sqlite_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def read_single_row(
    path: Path,
    *,
    layer: str,
    key_column: str,
    key_value: Any,
    columns: Sequence[str] | None = None,
    read_geometry: bool = False,
) -> pd.Series:
    if not path.exists():
        raise KeyError(str(path))

    where = f'"{key_column}" = {sqlite_literal(key_value)}'
    frame = pyogrio.read_dataframe(
        path,
        layer=layer,
        columns=list(columns) if columns else None,
        where=where,
        read_geometry=read_geometry,
    )

    if frame.empty:
        raise KeyError(str(key_value))
    return frame.iloc[0]


def ensure_attribute_index(path: Path, *, layer: str, column: str) -> None:
    if not path.exists():
        return
    index_name = f"idx_{layer}_{column}".replace("-", "_")
    with sqlite3.connect(path) as connection:
        connection.execute(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{layer}" ("{column}")'
        )
        connection.commit()


def write_geopackage_atomic(
    *,
    path: Path,
    layers: Iterable[tuple[str, gpd.GeoDataFrame]],
    indexes: Iterable[tuple[str, str]] = (),
) -> list[str]:
    """Write all non-empty layers to a temporary GPKG and atomically publish it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp.gpkg")
    written: list[str] = []

    try:
        for layer_name, frame in layers:
            if frame.empty:
                continue
            frame.to_file(
                temporary,
                layer=layer_name,
                driver="GPKG",
                mode="w" if not written else "a",
                index=False,
            )
            written.append(layer_name)

        if not written:
            raise RuntimeError("No non-empty GeoPackage layers were produced.")

        for layer_name, column in indexes:
            if layer_name in written:
                ensure_attribute_index(temporary, layer=layer_name, column=column)

        temporary.replace(path)
        return written
    finally:
        temporary.unlink(missing_ok=True)
        Path(str(temporary) + "-wal").unlink(missing_ok=True)
        Path(str(temporary) + "-shm").unlink(missing_ok=True)
