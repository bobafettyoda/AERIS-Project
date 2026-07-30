from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[2]
)

PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent

load_dotenv(
    BACKEND_DIRECTORY / ".env"
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def human_bytes(value: int | float) -> str:
    size = float(value)

    for unit in (
        "B",
        "KB",
        "MB",
        "GB",
    ):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}"

        size /= 1024

    return f"{size:,.1f} GB"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def chunked(
    values: Sequence[int],
    chunk_size: int,
) -> Iterable[list[int]]:
    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be positive."
        )

    for start in range(
        0,
        len(values),
        chunk_size,
    ):
        yield list(
            values[
                start : start
                + chunk_size
            ]
        )


def atomic_write_text(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        text,
        encoding="utf-8",
    )

    temporary.replace(path)


def atomic_write_json(
    path: Path,
    value: Any,
) -> None:
    atomic_write_text(
        path,
        json.dumps(
            value,
            indent=2,
        )
        + "\n",
    )


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=(
            "GET",
            "POST",
            "HEAD",
        ),
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": "AERIS/0.2",
        }
    )

    return session


def load_sources_config(
    config_path: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    if "sources" not in config:
        raise RuntimeError(
            "The source configuration "
            "does not contain 'sources'."
        )

    if "manifest" not in config:
        raise RuntimeError(
            "The source configuration "
            "does not contain 'manifest'."
        )

    return config


def parse_acs_response(
    rows: Any,
    variables: dict[str, str],
) -> pd.DataFrame:
    if (
        not isinstance(rows, list)
        or len(rows) < 2
    ):
        raise RuntimeError(
            "ACS returned no tract records."
        )

    headers = rows[0]

    if not isinstance(headers, list):
        raise RuntimeError(
            "ACS response header is invalid."
        )

    frame = pd.DataFrame(
        rows[1:],
        columns=headers,
    )

    required = {
        "state",
        "county",
        "tract",
        *variables.keys(),
    }

    missing = required - set(
        frame.columns
    )

    if missing:
        raise RuntimeError(
            "ACS response is missing: "
            + ", ".join(
                sorted(missing)
            )
        )

    frame = frame.rename(
        columns=variables
    )

    frame["GEOID"] = (
        frame["state"].astype(str)
        + frame["county"].astype(str)
        + frame["tract"].astype(str)
    )

    for column in (
        "population",
        "population_moe",
    ):
        if column in frame:
            frame[column] = (
                pd.to_numeric(
                    frame[column],
                    errors="coerce",
                )
            )

    preferred_columns = [
        "GEOID",
        "state",
        "county",
        "tract",
        *variables.values(),
    ]

    frame = frame[
        list(
            dict.fromkeys(
                preferred_columns
            )
        )
    ]

    if not frame["GEOID"].is_unique:
        raise RuntimeError(
            "ACS tract GEOIDs are "
            "not unique."
        )

    return frame.sort_values(
        "GEOID"
    ).reset_index(drop=True)


class ProgressReporter:
    def __init__(self) -> None:
        self.started_at = (
            time.monotonic()
        )

        self.last_printed_at = 0.0
        self.last_percent = -1

    def update(
        self,
        label: str,
        current: int,
        total: int | None,
        force: bool = False,
    ) -> None:
        now = time.monotonic()

        if total and total > 0:
            percent = int(
                current / total * 100
            )
        else:
            percent = -1

        should_print = (
            force
            or now
            - self.last_printed_at
            >= 1.0
            or (
                percent >= 0
                and percent
                >= self.last_percent + 5
            )
        )

        if not should_print:
            return

        elapsed = (
            now - self.started_at
        )

        if (
            total
            and total > 0
            and current > 0
        ):
            rate = current / elapsed
            remaining = total - current
            eta = (
                remaining / rate
                if rate > 0
                else 0
            )

            progress_text = (
                f"{current:,} / "
                f"{total:,} "
                f"({current / total * 100:5.1f}%)"
            )

            eta_text = (
                f"ETA {eta:,.1f}s"
            )
        else:
            progress_text = (
                f"{current:,}"
            )

            eta_text = ""

        print(
            (
                f"{label} "
                f"{progress_text} | "
                f"elapsed {elapsed:,.1f}s "
                f"{eta_text}"
            ).rstrip(),
            flush=True,
        )

        self.last_printed_at = now

        if percent >= 0:
            self.last_percent = percent


class FoundationAcquirer:
    SOURCE_NAMES = (
        "tiger_tracts",
        "acs_population",
        "md_enviroscreen",
    )

    def __init__(
        self,
        config_path: Path,
    ) -> None:
        self.config_path = (
            config_path.resolve()
        )

        self.config = load_sources_config(
            self.config_path
        )

        self.project_directory = (
            self.config_path.parents[2]
        )

        self.sources = (
            self.config["sources"]
        )

        self.manifest_path = (
            self.project_directory
            / self.config[
                "manifest"
            ]["path"]
        ).resolve()

        self.session = build_session()

        self.manifest = (
            self._load_manifest()
        )

    def _load_manifest(
        self,
    ) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {
                "schema_version": 1,
                "project": "AERIS",
                "pipeline": (
                    "statewide_foundations"
                ),
                "sources": {},
            }

        try:
            value = json.loads(
                self.manifest_path
                .read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(
                value,
                dict,
            ):
                raise ValueError

            value.setdefault(
                "sources",
                {},
            )

            return value
        except (
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "The acquisition manifest "
                "is invalid."
            ) from error

    def _save_manifest(
        self,
    ) -> None:
        self.manifest[
            "updated_at_utc"
        ] = utc_now()

        atomic_write_json(
            self.manifest_path,
            self.manifest,
        )

    def _resolve_output(
        self,
        source_name: str,
    ) -> Path:
        return (
            self.project_directory
            / self.sources[
                source_name
            ]["output"]
        ).resolve()

    def _source_entry(
        self,
        source_name: str,
    ) -> dict[str, Any]:
        return self.manifest[
            "sources"
        ].setdefault(
            source_name,
            {},
        )

    def _record_success(
        self,
        source_name: str,
        output_path: Path,
        record_count: int,
        metadata: dict[str, Any],
    ) -> None:
        entry = self._source_entry(
            source_name
        )

        entry.clear()

        entry.update(
            {
                "status": "complete",
                "retrieved_at_utc": (
                    utc_now()
                ),
                "source": (
                    self.sources[
                        source_name
                    ]
                ),
                "file": str(
                    output_path
                    .relative_to(
                        self.project_directory
                    )
                ),
                "size_bytes": (
                    output_path
                    .stat()
                    .st_size
                ),
                "sha256": (
                    sha256_file(
                        output_path
                    )
                ),
                "record_count": (
                    record_count
                ),
                "validation": (
                    metadata
                ),
            }
        )

        self._save_manifest()

    def _record_failure(
        self,
        source_name: str,
        error: Exception,
    ) -> None:
        entry = self._source_entry(
            source_name
        )

        entry.update(
            {
                "status": "error",
                "failed_at_utc": (
                    utc_now()
                ),
                "error_type": (
                    type(error).__name__
                ),
                "error": str(error),
            }
        )

        self._save_manifest()

    def _download_stream(
        self,
        url: str,
        output_path: Path,
        resume: bool,
    ) -> None:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        part_path = output_path.with_suffix(
            output_path.suffix + ".part"
        )

        starting_size = 0
        headers: dict[str, str] = {}

        if (
            resume
            and part_path.exists()
        ):
            starting_size = (
                part_path.stat().st_size
            )

            if starting_size > 0:
                headers[
                    "Range"
                ] = (
                    f"bytes={starting_size}-"
                )

        response = self.session.get(
            url,
            headers=headers,
            stream=True,
            timeout=180,
        )

        if (
            starting_size > 0
            and response.status_code
            != 206
        ):
            response.close()
            part_path.unlink(
                missing_ok=True
            )

            starting_size = 0

            response = self.session.get(
                url,
                stream=True,
                timeout=180,
            )

        response.raise_for_status()

        content_length = int(
            response.headers.get(
                "content-length",
                0,
            )
            or 0
        )

        total_size = (
            starting_size
            + content_length
            if content_length > 0
            else None
        )

        mode = (
            "ab"
            if starting_size > 0
            else "wb"
        )

        downloaded = starting_size
        reporter = ProgressReporter()

        reporter.update(
            "[Download]",
            downloaded,
            total_size,
            force=True,
        )

        with part_path.open(mode) as file:
            for block in (
                response.iter_content(
                    chunk_size=(
                        1024 * 1024
                    )
                )
            ):
                if not block:
                    continue

                file.write(block)
                downloaded += len(block)

                reporter.update(
                    "[Download]",
                    downloaded,
                    total_size,
                )

        reporter.update(
            "[Download]",
            downloaded,
            total_size,
            force=True,
        )

        part_path.replace(
            output_path
        )

    def validate_tiger(
        self,
    ) -> dict[str, Any]:
        source = self.sources[
            "tiger_tracts"
        ]

        output = self._resolve_output(
            "tiger_tracts"
        )

        if not output.exists():
            raise RuntimeError(
                "TIGER tract archive "
                "does not exist."
            )

        frame = gpd.read_file(
            f"zip://{output}"
        )

        required = {
            "GEOID",
            "STATEFP",
            "COUNTYFP",
            "TRACTCE",
            "ALAND",
        }

        missing = required - set(
            frame.columns
        )

        if missing:
            raise RuntimeError(
                "TIGER tracts are missing: "
                + ", ".join(
                    sorted(missing)
                )
            )

        expected_state = str(
            source[
                "expected_state_fips"
            ]
        )

        states = set(
            frame[
                "STATEFP"
            ].astype(str)
        )

        if states != {
            expected_state
        }:
            raise RuntimeError(
                "TIGER tract archive "
                "contains unexpected states: "
                + ", ".join(
                    sorted(states)
                )
            )

        if not frame[
            "GEOID"
        ].astype(str).is_unique:
            raise RuntimeError(
                "TIGER tract GEOIDs "
                "are not unique."
            )

        if frame.geometry.isna().any():
            raise RuntimeError(
                "TIGER tract archive "
                "contains missing geometry."
            )

        return {
            "record_count": len(frame),
            "crs": str(frame.crs),
            "state_fips": expected_state,
            "geoid_unique": True,
            "geometry_complete": True,
            "size_human": human_bytes(
                output.stat().st_size
            ),
        }

    def acquire_tiger(
        self,
        refresh: bool,
        resume: bool,
    ) -> dict[str, Any]:
        source_name = "tiger_tracts"
        source = self.sources[
            source_name
        ]

        output = self._resolve_output(
            source_name
        )

        if refresh:
            output.unlink(
                missing_ok=True
            )

            output.with_suffix(
                output.suffix + ".part"
            ).unlink(
                missing_ok=True
            )

        if not output.exists():
            print(
                "[1/3] Downloading "
                "Maryland TIGER tracts",
                flush=True,
            )

            self._download_stream(
                url=str(source["url"]),
                output_path=output,
                resume=resume,
            )
        else:
            print(
                "[1/3] Using cached "
                "Maryland TIGER tracts",
                flush=True,
            )

        validation = (
            self.validate_tiger()
        )

        self._record_success(
            source_name=source_name,
            output_path=output,
            record_count=int(
                validation[
                    "record_count"
                ]
            ),
            metadata=validation,
        )

        return validation

    def _census_api_key(
        self,
    ) -> str:
        key = os.getenv(
            "CENSUS_API_KEY",
            "",
        ).strip()

        if not key:
            raise RuntimeError(
                "CENSUS_API_KEY is not "
                "available in backend/.env."
            )

        return key

    def validate_acs(
        self,
    ) -> dict[str, Any]:
        output = self._resolve_output(
            "acs_population"
        )

        if not output.exists():
            raise RuntimeError(
                "ACS population snapshot "
                "does not exist."
            )

        frame = pd.read_csv(
            output,
            dtype={
                "GEOID": str,
                "state": str,
                "county": str,
                "tract": str,
            },
        )

        required = {
            "GEOID",
            "population",
            "population_moe",
        }

        missing = required - set(
            frame.columns
        )

        if missing:
            raise RuntimeError(
                "ACS snapshot is missing: "
                + ", ".join(
                    sorted(missing)
                )
            )

        if not frame[
            "GEOID"
        ].is_unique:
            raise RuntimeError(
                "ACS tract GEOIDs "
                "are not unique."
            )

        if (
            frame["population"]
            .isna()
            .any()
        ):
            raise RuntimeError(
                "ACS population contains "
                "missing estimates."
            )

        if (
            frame["population"] < 0
        ).any():
            raise RuntimeError(
                "ACS population contains "
                "negative estimates."
            )

        return {
            "record_count": len(frame),
            "geoid_unique": True,
            "population_complete": True,
            "population_total": int(
                frame[
                    "population"
                ].sum()
            ),
            "size_human": human_bytes(
                output.stat().st_size
            ),
        }

    def acquire_acs(
        self,
        refresh: bool,
    ) -> dict[str, Any]:
        source_name = "acs_population"
        source = self.sources[
            source_name
        ]

        output = self._resolve_output(
            source_name
        )

        if refresh:
            output.unlink(
                missing_ok=True
            )

        if not output.exists():
            print(
                "[2/3] Fetching statewide "
                "ACS tract population",
                flush=True,
            )

            variable_map = dict(
                source["variables"]
            )

            parameters = [
                (
                    "get",
                    ",".join(
                        variable_map.keys()
                    ),
                ),
                (
                    "for",
                    source[
                        "geography"
                    ]["for"],
                ),
                (
                    "in",
                    source[
                        "geography"
                    ]["in"],
                ),
                (
                    "key",
                    self._census_api_key(),
                ),
            ]

            response = self.session.get(
                str(source["url"]),
                params=parameters,
                timeout=120,
                allow_redirects=False,
            )

            if (
                300
                <= response.status_code
                < 400
            ):
                raise RuntimeError(
                    "Census API redirected "
                    "the request. Verify the "
                    "Census API key."
                )

            response.raise_for_status()

            content_type = (
                response.headers.get(
                    "content-type",
                    "",
                ).lower()
            )

            if "json" not in content_type:
                raise RuntimeError(
                    "Census API returned "
                    "a non-JSON response."
                )

            frame = parse_acs_response(
                rows=response.json(),
                variables=variable_map,
            )

            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary = output.with_suffix(
                output.suffix + ".tmp"
            )

            frame.to_csv(
                temporary,
                index=False,
                quoting=csv.QUOTE_MINIMAL,
            )

            temporary.replace(output)

            print(
                (
                    "[ACS] "
                    f"{len(frame):,} tract "
                    "records written"
                ),
                flush=True,
            )
        else:
            print(
                "[2/3] Using cached "
                "ACS tract population",
                flush=True,
            )

        validation = (
            self.validate_acs()
        )

        self._record_success(
            source_name=source_name,
            output_path=output,
            record_count=int(
                validation[
                    "record_count"
                ]
            ),
            metadata=validation,
        )

        return validation

    def _enviroscreen_metadata(
        self,
    ) -> dict[str, Any]:
        source = self.sources[
            "md_enviroscreen"
        ]

        response = self.session.get(
            str(source["layer_url"]),
            params={
                "f": "json",
            },
            timeout=120,
        )

        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            raise RuntimeError(
                "MD EnviroScreen metadata "
                f"error: {payload['error']}"
            )

        return payload

    def _enviroscreen_ids(
        self,
    ) -> tuple[
        str,
        list[int],
        dict[str, Any],
    ]:
        source = self.sources[
            "md_enviroscreen"
        ]

        metadata = (
            self._enviroscreen_metadata()
        )

        object_id_field = str(
            metadata.get(
                "objectIdField",
                metadata.get(
                    "objectIdFieldName",
                    "OBJECTID",
                ),
            )
        )

        available_fields = {
            str(field["name"])
            for field in metadata.get(
                "fields",
                [],
            )
            if "name" in field
        }

        requested_fields = set(
            source["fields"]
        )

        missing = (
            requested_fields
            - available_fields
        )

        if missing:
            raise RuntimeError(
                "MD EnviroScreen does not "
                "contain requested fields: "
                + ", ".join(
                    sorted(missing)
                )
            )

        response = self.session.post(
            (
                f"{source['layer_url']}"
                "/query"
            ),
            data={
                "where": "1=1",
                "returnIdsOnly": "true",
                "f": "json",
            },
            timeout=120,
        )

        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            raise RuntimeError(
                "MD EnviroScreen object-ID "
                f"query failed: {payload['error']}"
            )

        object_ids = sorted(
            int(value)
            for value in (
                payload.get(
                    "objectIds"
                )
                or []
            )
        )

        if not object_ids:
            raise RuntimeError(
                "MD EnviroScreen returned "
                "no object IDs."
            )

        return (
            object_id_field,
            object_ids,
            metadata,
        )

    def validate_enviroscreen(
        self,
    ) -> dict[str, Any]:
        output = self._resolve_output(
            "md_enviroscreen"
        )

        if not output.exists():
            raise RuntimeError(
                "MD EnviroScreen snapshot "
                "does not exist."
            )

        payload = json.loads(
            output.read_text(
                encoding="utf-8"
            )
        )

        if (
            payload.get("type")
            != "FeatureCollection"
        ):
            raise RuntimeError(
                "MD EnviroScreen snapshot "
                "is not a FeatureCollection."
            )

        features = payload.get(
            "features",
            [],
        )

        if not features:
            raise RuntimeError(
                "MD EnviroScreen snapshot "
                "contains no features."
            )

        geoids = [
            str(
                feature.get(
                    "properties",
                    {},
                ).get(
                    "GEOID20",
                    "",
                )
            )
            for feature in features
        ]

        missing_geoids = [
            value
            for value in geoids
            if not value
        ]

        if missing_geoids:
            raise RuntimeError(
                "MD EnviroScreen snapshot "
                "contains missing GEOID20 values."
            )

        if (
            len(set(geoids))
            != len(geoids)
        ):
            raise RuntimeError(
                "MD EnviroScreen GEOID20 "
                "values are not unique."
            )

        if any(
            not feature.get(
                "geometry"
            )
            for feature in features
        ):
            raise RuntimeError(
                "MD EnviroScreen contains "
                "missing geometry."
            )

        return {
            "record_count": len(features),
            "geoid_unique": True,
            "geometry_complete": True,
            "size_human": human_bytes(
                output.stat().st_size
            ),
        }

    def acquire_enviroscreen(
        self,
        refresh: bool,
        resume: bool,
    ) -> dict[str, Any]:
        source_name = "md_enviroscreen"

        source = self.sources[
            source_name
        ]

        output = self._resolve_output(
            source_name
        )

        page_directory = (
            self.project_directory
            / source[
                "page_directory"
            ]
        ).resolve()

        if refresh:
            output.unlink(
                missing_ok=True
            )

            shutil.rmtree(
                page_directory,
                ignore_errors=True,
            )

        if not output.exists():
            print(
                "[3/3] Downloading "
                "MD EnviroScreen",
                flush=True,
            )

            (
                object_id_field,
                object_ids,
                metadata,
            ) = self._enviroscreen_ids()

            page_size = int(
                source["page_size"]
            )

            pages = list(
                chunked(
                    object_ids,
                    page_size,
                )
            )

            page_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            reporter = ProgressReporter()

            all_features: list[
                dict[str, Any]
            ] = []

            for page_index, page_ids in (
                enumerate(
                    pages,
                    start=1,
                )
            ):
                page_path = (
                    page_directory
                    / (
                        f"page_"
                        f"{page_index:04d}"
                        ".geojson"
                    )
                )

                page_payload: dict[
                    str,
                    Any,
                ]

                if (
                    resume
                    and page_path.exists()
                ):
                    page_payload = (
                        json.loads(
                            page_path.read_text(
                                encoding="utf-8"
                            )
                        )
                    )
                else:
                    response = (
                        self.session.post(
                            (
                                f"{source['layer_url']}"
                                "/query"
                            ),
                            data={
                                "objectIds": (
                                    ",".join(
                                        str(value)
                                        for value
                                        in page_ids
                                    )
                                ),
                                "outFields": (
                                    ",".join(
                                        source[
                                            "fields"
                                        ]
                                    )
                                ),
                                "returnGeometry": (
                                    "true"
                                ),
                                "outSR": "4326",
                                "f": "geojson",
                            },
                            timeout=180,
                        )
                    )

                    response.raise_for_status()

                    page_payload = (
                        response.json()
                    )

                    if "error" in page_payload:
                        raise RuntimeError(
                            "MD EnviroScreen "
                            "page query failed: "
                            f"{page_payload['error']}"
                        )

                    atomic_write_json(
                        page_path,
                        page_payload,
                    )

                page_features = (
                    page_payload.get(
                        "features",
                        [],
                    )
                )

                all_features.extend(
                    page_features
                )

                reporter.update(
                    "[EnviroScreen]",
                    min(
                        page_index
                        * page_size,
                        len(object_ids),
                    ),
                    len(object_ids),
                    force=True,
                )

            feature_collection = {
                "type": (
                    "FeatureCollection"
                ),
                "features": (
                    all_features
                ),
                "properties": {
                    "source_layer": (
                        source[
                            "layer_url"
                        ]
                    ),
                    "source_last_updated": (
                        source.get(
                            "source_last_updated"
                        )
                    ),
                    "object_id_field": (
                        object_id_field
                    ),
                    "source_object_count": (
                        len(object_ids)
                    ),
                    "service_max_record_count": (
                        metadata.get(
                            "maxRecordCount"
                        )
                    ),
                    "retrieved_at_utc": (
                        utc_now()
                    ),
                },
            }

            atomic_write_json(
                output,
                feature_collection,
            )

            print(
                (
                    "[EnviroScreen] "
                    f"{len(all_features):,} "
                    "features written"
                ),
                flush=True,
            )
        else:
            print(
                "[3/3] Using cached "
                "MD EnviroScreen",
                flush=True,
            )

        validation = (
            self.validate_enviroscreen()
        )

        self._record_success(
            source_name=source_name,
            output_path=output,
            record_count=int(
                validation[
                    "record_count"
                ]
            ),
            metadata=validation,
        )

        return validation

    def validate(
        self,
        source_names: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        results: dict[
            str,
            dict[str, Any],
        ] = {}

        for source_name in source_names:
            print(
                (
                    "[Validate] "
                    f"{source_name}"
                ),
                flush=True,
            )

            if (
                source_name
                == "tiger_tracts"
            ):
                result = (
                    self.validate_tiger()
                )

            elif (
                source_name
                == "acs_population"
            ):
                result = (
                    self.validate_acs()
                )

            elif (
                source_name
                == "md_enviroscreen"
            ):
                result = (
                    self
                    .validate_enviroscreen()
                )

            else:
                raise ValueError(
                    f"Unknown source: {source_name}"
                )

            results[source_name] = (
                result
            )

            print(
                json.dumps(
                    result,
                    indent=2,
                ),
                flush=True,
            )

        return results

    def acquire(
        self,
        source_names: Sequence[str],
        refresh: bool = False,
        resume: bool = False,
    ) -> dict[str, dict[str, Any]]:
        results: dict[
            str,
            dict[str, Any],
        ] = {}

        for source_name in source_names:
            try:
                if (
                    source_name
                    == "tiger_tracts"
                ):
                    result = (
                        self.acquire_tiger(
                            refresh=refresh,
                            resume=resume,
                        )
                    )

                elif (
                    source_name
                    == "acs_population"
                ):
                    result = (
                        self.acquire_acs(
                            refresh=refresh,
                        )
                    )

                elif (
                    source_name
                    == "md_enviroscreen"
                ):
                    result = (
                        self
                        .acquire_enviroscreen(
                            refresh=refresh,
                            resume=resume,
                        )
                    )

                else:
                    raise ValueError(
                        "Unknown source: "
                        f"{source_name}"
                    )

                results[source_name] = (
                    result
                )

            except Exception as error:
                self._record_failure(
                    source_name,
                    error,
                )

                raise

        return results

    def status(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "manifest": str(
                self.manifest_path
            ),
            "sources": {},
        }

        for source_name in (
            self.SOURCE_NAMES
        ):
            output = self._resolve_output(
                source_name
            )

            manifest_entry = (
                self.manifest.get(
                    "sources",
                    {},
                ).get(
                    source_name,
                    {},
                )
            )

            report["sources"][
                source_name
            ] = {
                "file_exists": (
                    output.exists()
                ),
                "file": str(
                    output.relative_to(
                        self.project_directory
                    )
                ),
                "size_bytes": (
                    output.stat().st_size
                    if output.exists()
                    else 0
                ),
                "manifest_status": (
                    manifest_entry.get(
                        "status",
                        "not_recorded",
                    )
                ),
                "record_count": (
                    manifest_entry.get(
                        "record_count"
                    )
                ),
                "retrieved_at_utc": (
                    manifest_entry.get(
                        "retrieved_at_utc"
                    )
                ),
            }

        return report
