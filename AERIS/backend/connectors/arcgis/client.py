from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(
    *,
    user_agent: str = "AERIS/0.6.1 arcgis-client",
    retry_count: int = 5,
) -> requests.Session:
    retry = Retry(
        total=retry_count,
        connect=retry_count,
        read=retry_count,
        status=retry_count,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    data: dict[str, str] | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    if data is None:
        response = session.get(url, params={"f": "json"}, timeout=timeout_seconds)
    else:
        response = session.post(url, data=data, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        error = payload["error"]
        raise RuntimeError(
            f"{url}: {error.get('code')} - {error.get('message')}"
        )
    return payload


def chunks(values: Sequence[int], size: int) -> list[list[int]]:
    return [list(values[start : start + size]) for start in range(0, len(values), size)]


def selected_fields(
    metadata: dict[str, Any],
    desired: Sequence[str],
) -> tuple[str, list[str]]:
    field_metadata = [
        field
        for field in metadata.get("fields", [])
        if isinstance(field, dict) and field.get("name")
    ]
    object_id_field = str(
        metadata.get("objectIdField")
        or metadata.get("objectIdFieldName")
        or ""
    ).strip()

    if not object_id_field:
        oid_fields = [
            str(field["name"])
            for field in field_metadata
            if str(field.get("type", "")).lower() == "esrifieldtypeoid"
        ]
        if len(oid_fields) == 1:
            object_id_field = oid_fields[0]
        elif len(oid_fields) > 1:
            raise RuntimeError(
                "ArcGIS metadata identifies multiple object-ID fields: "
                + ", ".join(oid_fields)
            )

    if not object_id_field:
        available = [
            f"{field.get('name')} ({field.get('type')})" for field in field_metadata
        ]
        raise RuntimeError(
            "ArcGIS metadata does not identify an object-ID field. Available fields: "
            + ", ".join(available)
        )

    available_lookup = {
        str(field["name"]).upper(): str(field["name"]) for field in field_metadata
    }
    object_id_field = available_lookup.get(object_id_field.upper(), object_id_field)
    fields = [object_id_field]
    for desired_name in desired:
        actual = available_lookup.get(str(desired_name).upper())
        if actual and actual not in fields:
            fields.append(actual)
    return object_id_field, fields


def object_ids_in_envelope(
    session: requests.Session,
    layer_url: str,
    envelope: dict[str, float] | None,
    where: str = "1=1",
) -> list[int]:
    data: dict[str, str] = {
        "where": where,
        "returnIdsOnly": "true",
        "f": "json",
    }
    if envelope is not None:
        data.update(
            {
                "geometry": json.dumps(
                    {**envelope, "spatialReference": {"wkid": 4326}}
                ),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )

    payload = request_json(
        session,
        f"{layer_url.rstrip('/')}/query",
        data=data,
    )
    object_ids = sorted(int(value) for value in (payload.get("objectIds") or []))
    if not object_ids:
        query_type = "attribute-only" if envelope is None else "spatial"
        raise RuntimeError(
            f"ArcGIS {query_type} query returned no object IDs for where={where!r}."
        )
    return object_ids


def feature_collection_to_frame(
    features: list[dict[str, Any]],
) -> gpd.GeoDataFrame:
    if not features:
        raise RuntimeError("No ArcGIS features were downloaded.")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    frame = frame.loc[
        frame.geometry.notna() & ~frame.geometry.is_empty
    ].copy()
    if frame.empty:
        raise RuntimeError("Downloaded features contain no usable geometry.")
    frame.geometry = frame.geometry.make_valid()
    return frame


def query_feature_batch(
    *,
    session: requests.Session,
    layer_url: str,
    object_ids: Sequence[int],
    output_fields: Sequence[str],
    name: str,
    depth: int = 0,
) -> list[dict[str, Any]]:
    ids = [int(value) for value in object_ids]
    if not ids:
        return []
    try:
        payload = request_json(
            session,
            f"{layer_url.rstrip('/')}/query",
            data={
                "objectIds": ",".join(str(value) for value in ids),
                "outFields": ",".join(output_fields),
                "returnGeometry": "true",
                "returnTrueCurves": "false",
                "outSR": "4326",
                "geometryPrecision": "5",
                "f": "geojson",
            },
        )
        features = payload.get("features")
        if not isinstance(features, list):
            raise RuntimeError("ArcGIS response does not contain a feature list.")
        if len(features) != len(ids):
            raise RuntimeError(
                f"Requested {len(ids):,} object IDs but received {len(features):,} features."
            )
        return features
    except (requests.RequestException, RuntimeError) as error:
        if len(ids) == 1:
            raise RuntimeError(
                f"{name}: ArcGIS failed for object ID {ids[0]} after adaptive splitting."
            ) from error
        midpoint = len(ids) // 2
        left_ids, right_ids = ids[:midpoint], ids[midpoint:]
        indentation = "      " + "  " * depth
        print(
            f"{indentation}[{name}] batch of {len(ids):,} failed; "
            f"splitting into {len(left_ids):,} + {len(right_ids):,}",
            flush=True,
        )
        return query_feature_batch(
            session=session,
            layer_url=layer_url,
            object_ids=left_ids,
            output_fields=output_fields,
            name=name,
            depth=depth + 1,
        ) + query_feature_batch(
            session=session,
            layer_url=layer_url,
            object_ids=right_ids,
            output_fields=output_fields,
            name=name,
            depth=depth + 1,
        )


@dataclass
class ArcGISClient:
    session: requests.Session
    timeout_seconds: int = 180

    @classmethod
    def create(
        cls,
        *,
        user_agent: str = "AERIS/0.6.1 arcgis-client",
        retry_count: int = 5,
        timeout_seconds: int = 180,
    ) -> "ArcGISClient":
        return cls(
            session=build_session(user_agent=user_agent, retry_count=retry_count),
            timeout_seconds=timeout_seconds,
        )

    def metadata(self, layer_url: str) -> dict[str, Any]:
        return request_json(
            self.session,
            layer_url,
            timeout_seconds=self.timeout_seconds,
        )
