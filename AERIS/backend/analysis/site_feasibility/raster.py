from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import requests
import rasterio
from affine import Affine
from rasterio.features import geometry_mask, shapes
from rasterio.merge import merge
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape

from analysis.common.geometry import repair_invalid_geometries
from analysis.common.io import atomic_write_json, read_json
from connectors.arcgis.client import build_session, request_json


@dataclass(frozen=True)
class TerrainRasterPaths:
    dem: Path
    slope: Path
    metadata: Path
    tiles_directory: Path


def choose_pixel_size(
    bounds: tuple[float, float, float, float],
    *,
    target_pixel_size_m: float,
    maximum_pixel_size_m: float,
    maximum_total_pixels: int,
) -> float:
    west, south, east, north = bounds
    width_m = max(0.0, east - west)
    height_m = max(0.0, north - south)
    if width_m <= 0 or height_m <= 0:
        raise ValueError("Terrain bounds must have positive width and height.")

    pixel_size = float(target_pixel_size_m)
    estimated_pixels = (width_m / pixel_size) * (height_m / pixel_size)
    if estimated_pixels > maximum_total_pixels:
        pixel_size = math.sqrt(
            width_m * height_m / float(maximum_total_pixels)
        )

    maximum_pixel_size = float(maximum_pixel_size_m)
    if pixel_size > maximum_pixel_size:
        pixels_at_maximum = (
            width_m / maximum_pixel_size
        ) * (
            height_m / maximum_pixel_size
        )
        raise ValueError(
            "Terrain scope exceeds the configured raster budget even at "
            f"{maximum_pixel_size:g} m resolution "
            f"({pixels_at_maximum:,.0f} pixels > "
            f"{int(maximum_total_pixels):,}). Use a smaller parcel scope."
        )

    return max(float(target_pixel_size_m), pixel_size)


def tile_bounds(
    bounds: tuple[float, float, float, float],
    *,
    pixel_size_m: float,
    maximum_tile_pixels: int,
) -> list[tuple[float, float, float, float]]:
    west, south, east, north = bounds
    tile_span = pixel_size_m * int(maximum_tile_pixels)
    x_count = max(1, math.ceil((east - west) / tile_span))
    y_count = max(1, math.ceil((north - south) / tile_span))
    result: list[tuple[float, float, float, float]] = []
    for row in range(y_count):
        tile_south = south + row * tile_span
        tile_north = min(north, tile_south + tile_span)
        for column in range(x_count):
            tile_west = west + column * tile_span
            tile_east = min(east, tile_west + tile_span)
            result.append(
                (tile_west, tile_south, tile_east, tile_north)
            )
    return result


def _download_href(
    session: requests.Session,
    href: str,
    destination: Path,
    *,
    timeout_seconds: int,
) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with session.get(href, stream=True, timeout=timeout_seconds) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    output.write(block)
    temporary.replace(destination)


def export_image_tile(
    *,
    session: requests.Session,
    image_server_url: str,
    bounds: tuple[float, float, float, float],
    pixel_size_m: float,
    target_crs_wkid: int,
    raster_function: str,
    output_path: Path,
    timeout_seconds: int,
) -> None:
    west, south, east, north = bounds
    width = max(1, int(math.ceil((east - west) / pixel_size_m)))
    height = max(1, int(math.ceil((north - south) / pixel_size_m)))
    payload = request_json(
        session,
        f"{image_server_url.rstrip('/')}/exportImage",
        data={
            "bbox": f"{west},{south},{east},{north}",
            "bboxSR": str(target_crs_wkid),
            "imageSR": str(target_crs_wkid),
            "size": f"{width},{height}",
            "format": "tiff",
            "pixelType": "F32",
            "interpolation": "RSP_BilinearInterpolation",
            "renderingRule": (
                "{}"
                if raster_function in {"", "None", "none"}
                else '{"rasterFunction":"' + raster_function + '"}'
            ),
            "f": "json",
        },
        timeout_seconds=timeout_seconds,
    )
    href = str(payload.get("href") or "").strip()
    if not href:
        raise RuntimeError(
            "ImageServer export response did not contain a download URL."
        )
    _download_href(
        session,
        href,
        output_path,
        timeout_seconds=timeout_seconds,
    )


def compute_slope_percent(
    dem: np.ndarray,
    *,
    transform: Affine,
    nodata: float | None,
) -> np.ndarray:
    values = dem.astype("float64", copy=True)
    invalid = ~np.isfinite(values)
    if nodata is not None and np.isfinite(nodata):
        invalid |= np.isclose(values, nodata)
    values[invalid] = np.nan

    pixel_x = abs(float(transform.a))
    pixel_y = abs(float(transform.e))
    if pixel_x <= 0 or pixel_y <= 0:
        raise ValueError("Raster transform has invalid pixel dimensions.")

    gradient_y, gradient_x = np.gradient(
        values,
        pixel_y,
        pixel_x,
    )
    slope = np.sqrt(
        np.square(gradient_x)
        + np.square(gradient_y)
    ) * 100.0
    slope[invalid] = np.nan
    return slope.astype("float32")


def export_scope_terrain(
    *,
    image_server_url: str,
    source_name: str,
    source_last_updated: str,
    bounds: tuple[float, float, float, float],
    target_crs_wkid: int,
    target_pixel_size_m: float,
    maximum_pixel_size_m: float,
    maximum_total_pixels: int,
    maximum_tile_pixels: int,
    raster_function: str,
    timeout_seconds: int,
    paths: TerrainRasterPaths,
    fingerprint: str,
    refresh: bool,
) -> dict[str, Any]:
    if refresh:
        paths.dem.unlink(missing_ok=True)
        paths.slope.unlink(missing_ok=True)
        paths.metadata.unlink(missing_ok=True)
        shutil.rmtree(paths.tiles_directory, ignore_errors=True)

    if (
        paths.dem.exists()
        and paths.slope.exists()
        and paths.metadata.exists()
    ):
        metadata = read_json(paths.metadata)
        if metadata.get("fingerprint") == fingerprint:
            metadata["used_cache"] = True
            return metadata

    pixel_size = choose_pixel_size(
        bounds,
        target_pixel_size_m=target_pixel_size_m,
        maximum_pixel_size_m=maximum_pixel_size_m,
        maximum_total_pixels=maximum_total_pixels,
    )
    tiles = tile_bounds(
        bounds,
        pixel_size_m=pixel_size,
        maximum_tile_pixels=maximum_tile_pixels,
    )
    paths.tiles_directory.mkdir(parents=True, exist_ok=True)
    session = build_session(
        user_agent="AERIS/0.7 terrain-export",
        retry_count=6,
    )
    tile_paths: list[Path] = []
    for index, tile in enumerate(tiles, start=1):
        tile_path = paths.tiles_directory / f"dem_{index:04d}.tif"
        if not tile_path.exists() or refresh:
            export_image_tile(
                session=session,
                image_server_url=image_server_url,
                bounds=tile,
                pixel_size_m=pixel_size,
                target_crs_wkid=target_crs_wkid,
                raster_function=raster_function,
                output_path=tile_path,
                timeout_seconds=timeout_seconds,
            )
        tile_paths.append(tile_path)
        print(
            f"      [terrain] tile {index:,}/{len(tiles):,}",
            flush=True,
        )

    datasets = [rasterio.open(path) for path in tile_paths]
    try:
        mosaic, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            count=1,
            dtype="float32",
            compress="deflate",
            tiled=True,
            BIGTIFF="IF_SAFER",
        )
        paths.dem.parent.mkdir(parents=True, exist_ok=True)
        temporary_dem = paths.dem.with_suffix(".tmp.tif")
        with rasterio.open(temporary_dem, "w", **profile) as output:
            output.write(mosaic[0].astype("float32"), 1)
        temporary_dem.replace(paths.dem)
    finally:
        for dataset in datasets:
            dataset.close()

    with rasterio.open(paths.dem) as dem_dataset:
        dem = dem_dataset.read(1)
        slope = compute_slope_percent(
            dem,
            transform=dem_dataset.transform,
            nodata=dem_dataset.nodata,
        )
        slope_profile = dem_dataset.profile.copy()
        slope_profile.update(
            dtype="float32",
            nodata=np.nan,
            compress="deflate",
            tiled=True,
            BIGTIFF="IF_SAFER",
        )
        temporary_slope = paths.slope.with_suffix(".tmp.tif")
        with rasterio.open(temporary_slope, "w", **slope_profile) as output:
            output.write(slope, 1)
        temporary_slope.replace(paths.slope)

    metadata = {
        "fingerprint": fingerprint,
        "source_name": source_name,
        "image_server_url": image_server_url,
        "source_last_updated": source_last_updated,
        "bounds": list(bounds),
        "target_crs_wkid": target_crs_wkid,
        "pixel_size_m": pixel_size,
        "tile_count": len(tiles),
        "dem_path": str(paths.dem),
        "slope_path": str(paths.slope),
        "used_cache": False,
    }
    atomic_write_json(paths.metadata, metadata)
    return metadata


def _safe_window(
    dataset: rasterio.io.DatasetReader,
    bounds: tuple[float, float, float, float],
) -> Window | None:
    window = from_bounds(
        *bounds,
        transform=dataset.transform,
    ).round_offsets().round_lengths()
    full = Window(
        col_off=0,
        row_off=0,
        width=dataset.width,
        height=dataset.height,
    )
    try:
        intersection = window.intersection(full)
    except rasterio.errors.WindowError:
        return None
    if intersection.width <= 0 or intersection.height <= 0:
        return None
    return intersection


def zonal_raster_statistics(
    *,
    geometries: Iterable,
    raster_path: Path,
    quantiles: tuple[float, ...] = (),
    thresholds: tuple[float, ...] = (),
) -> list[dict[str, float | int | None]]:
    results: list[dict[str, float | int | None]] = []
    with rasterio.open(raster_path) as dataset:
        for geometry in geometries:
            if geometry is None or geometry.is_empty:
                results.append(
                    {
                        "count": 0,
                        "minimum": None,
                        "maximum": None,
                        "mean": None,
                    }
                )
                continue
            window = _safe_window(dataset, geometry.bounds)
            if window is None:
                results.append(
                    {
                        "count": 0,
                        "minimum": None,
                        "maximum": None,
                        "mean": None,
                    }
                )
                continue
            data = dataset.read(1, window=window, masked=False)
            transform = dataset.window_transform(window)
            mask = geometry_mask(
                [geometry.__geo_interface__],
                out_shape=data.shape,
                transform=transform,
                invert=True,
                all_touched=False,
            )
            valid = mask & np.isfinite(data)
            if dataset.nodata is not None and np.isfinite(dataset.nodata):
                valid &= ~np.isclose(data, dataset.nodata)
            values = data[valid]
            if values.size == 0:
                results.append(
                    {
                        "count": 0,
                        "minimum": None,
                        "maximum": None,
                        "mean": None,
                    }
                )
                continue
            record: dict[str, float | int | None] = {
                "count": int(values.size),
                "minimum": float(np.nanmin(values)),
                "maximum": float(np.nanmax(values)),
                "mean": float(np.nanmean(values)),
            }
            for quantile in quantiles:
                record[f"q{int(round(quantile * 100)):02d}"] = float(
                    np.nanquantile(values, quantile)
                )
            for threshold in thresholds:
                key = str(threshold).replace(".", "_")
                record[f"fraction_ge_{key}"] = float(
                    np.count_nonzero(values >= threshold) / values.size
                )
            results.append(record)
    return results


def threshold_polygons(
    *,
    raster_path: Path,
    threshold: float,
    minimum_area_sq_m: float,
    clip_geometry=None,
) -> gpd.GeoDataFrame:
    records: list[dict[str, Any]] = []
    with rasterio.open(raster_path) as dataset:
        data = dataset.read(1, masked=False)
        valid = np.isfinite(data) & (data >= threshold)
        for geometry_mapping, value in shapes(
            valid.astype("uint8"),
            mask=valid,
            transform=dataset.transform,
        ):
            if int(value) != 1:
                continue
            geometry = shape(geometry_mapping)
            if clip_geometry is not None:
                geometry = geometry.intersection(clip_geometry)
            if geometry.is_empty or geometry.area < minimum_area_sq_m:
                continue
            records.append(
                {
                    "threshold": threshold,
                    "geometry": geometry,
                }
            )
        crs = dataset.crs
    if not records:
        return gpd.GeoDataFrame(
            {"threshold": [], "geometry": []},
            geometry="geometry",
            crs=crs,
        )
    frame = gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs=crs,
    )
    return repair_invalid_geometries(
        frame,
        name="steep_slope_polygons",
    )
