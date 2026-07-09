from __future__ import annotations

from typing import Any

import requests


def query_arcgis_geojson(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    result_record_count: int = 10,
    result_offset: int = 0,
    timeout: int = 30,
    geometry: str | None = None,
    geometry_type: str | None = None,
    spatial_rel: str = "esriSpatialRelIntersects",
) -> dict[str, Any]:
    """
    Query an ArcGIS REST layer and return GeoJSON.
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "f": "geojson",
        "returnGeometry": "true",
        "resultRecordCount": result_record_count,
        "resultOffset": result_offset,
    }

    if geometry:
        params.update(
            {
                "geometry": geometry,
                "geometryType": geometry_type or "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": spatial_rel,
            }
        )

    response = requests.get(
        f"{layer_url}/query",
        params=params,
        timeout=timeout,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"ArcGIS request failed with status {response.status_code}: {response.text[:500]}"
        ) from exc

    data = response.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS service error: {data['error']}")

    return data


def count_arcgis_features(
    layer_url: str,
    where: str = "1=1",
    timeout: int = 30,
) -> int:
    """
    Return feature count for an ArcGIS REST layer.
    """
    params = {
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }

    response = requests.get(
        f"{layer_url}/query",
        params=params,
        timeout=timeout,
    )

    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS service error: {data['error']}")

    return int(data["count"])
    
def query_arcgis_geojson_paged(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = 500,
    max_features: int | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Query an ArcGIS REST layer in pages and combine results into one GeoJSON FeatureCollection.
    """
    total_count = count_arcgis_features(layer_url, where=where, timeout=timeout)

    if max_features is not None:
        total_count = min(total_count, max_features)

    features = []
    offset = 0

    while offset < total_count:
        batch_size = min(page_size, total_count - offset)

        data = query_arcgis_geojson(
            layer_url=layer_url,
            where=where,
            out_fields=out_fields,
            result_record_count=batch_size,
            result_offset=offset,
            timeout=timeout,
        )

        features.extend(data.get("features", []))
        offset += batch_size

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source_count": total_count,
            "returned_count": len(features),
            "page_size": page_size,
        },
    }