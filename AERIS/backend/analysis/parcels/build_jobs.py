from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from analysis.common.io import atomic_write_json, read_json
from analysis.common.locking import file_lock
from analysis.parcels.api_service import ParcelDataService
from analysis.parcels.envelope_api_service import ParcelEnvelopeService
from analysis.parcels.grid_feasibility_api_service import (
    ParcelGridFeasibilityService,
)
from analysis.parcels.pipeline import (
    parcel_scope_paths,
    scope_from_bbox,
    scope_from_zone,
)
from analysis.planning.planning_api_service import PlanningContextService


ARTIFACT_NAMES = (
    "parcels",
    "envelopes",
    "grid",
    "planning",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_entry(state: str = "pending", error: str | None = None) -> dict[str, Any]:
    return {
        "state": state,
        "error": error,
        "updated_at_utc": utc_now(),
    }


class ScopeBuildCoordinator:
    """Coordinate expensive scoped GIS builds and persist progress to disk."""

    def __init__(
        self,
        *,
        parcel_service: ParcelDataService,
        envelope_service: ParcelEnvelopeService,
        grid_service: ParcelGridFeasibilityService,
        planning_service: PlanningContextService,
        runtime_directory: Path,
        max_workers: int = 2,
    ) -> None:
        self.parcel_service = parcel_service
        self.envelope_service = envelope_service
        self.grid_service = grid_service
        self.planning_service = planning_service
        self.runtime_directory = runtime_directory.resolve()
        self.jobs_directory = self.runtime_directory / "jobs"
        self.locks_directory = self.runtime_directory / "locks"
        self.jobs_directory.mkdir(parents=True, exist_ok=True)
        self.locks_directory.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="aeris-scope-build",
        )
        self._mutex = threading.Lock()
        self._active_scope_jobs: dict[str, str] = {}

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_directory / f"{job_id}.json"

    def _write(self, job: dict[str, Any]) -> None:
        job["updated_at_utc"] = utc_now()
        atomic_write_json(self._job_path(str(job["job_id"])), job)

    def get(self, job_id: str) -> dict[str, Any]:
        path = self._job_path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        return read_json(path)

    def _new_job(
        self,
        *,
        scope_id: str,
        target: dict[str, Any],
        refresh: bool,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "scope_id": scope_id,
            "state": "queued",
            "target": target,
            "refresh": refresh,
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "current_stage": "queued",
            "progress": 0.0,
            "artifacts": {
                name: artifact_entry() for name in ARTIFACT_NAMES
            },
            "warnings": [],
            "error": None,
        }
        self._write(job)
        return job

    def _existing_active_job(self, scope_id: str) -> dict[str, Any] | None:
        with self._mutex:
            job_id = self._active_scope_jobs.get(scope_id)
        if not job_id:
            return None
        try:
            job = self.get(job_id)
        except KeyError:
            return None
        if job.get("state") in {"queued", "running"}:
            return job
        return None

    def submit_zone(self, *, zone_id: str, refresh: bool = False) -> dict[str, Any]:
        scope = scope_from_zone(
            config=self.parcel_service.config,
            project_directory=self.parcel_service.project_directory,
            zone_id=zone_id,
        )
        existing = self._existing_active_job(scope.scope_id)
        if existing:
            return existing
        job = self._new_job(
            scope_id=scope.scope_id,
            target={"type": "zone", "zone_id": zone_id},
            refresh=refresh,
        )
        with self._mutex:
            self._active_scope_jobs[scope.scope_id] = str(job["job_id"])
        self.executor.submit(self._run, str(job["job_id"]))
        return job

    def submit_bbox(
        self,
        *,
        west: float,
        south: float,
        east: float,
        north: float,
        scope_name: str | None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        scope = scope_from_bbox(
            west=west,
            south=south,
            east=east,
            north=north,
            scope_name=scope_name,
        )
        existing = self._existing_active_job(scope.scope_id)
        if existing:
            return existing
        target = {
            "type": "bbox",
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "scope_name": scope_name,
        }
        job = self._new_job(scope_id=scope.scope_id, target=target, refresh=refresh)
        with self._mutex:
            self._active_scope_jobs[scope.scope_id] = str(job["job_id"])
        self.executor.submit(self._run, str(job["job_id"]))
        return job

    def _update_artifact(
        self,
        job: dict[str, Any],
        artifact: str,
        *,
        state: str,
        error: str | None = None,
    ) -> None:
        job["artifacts"][artifact] = artifact_entry(state=state, error=error)
        self._write(job)

    def _run_builder(
        self,
        job: dict[str, Any],
        artifact: str,
        progress: float,
        builder: Callable[[], Any],
    ) -> bool:
        job["current_stage"] = artifact
        job["progress"] = progress
        self._update_artifact(job, artifact, state="running")
        try:
            builder()
        except Exception as error:  # noqa: BLE001 - persisted as artifact failure
            self._update_artifact(
                job,
                artifact,
                state="failed",
                error=f"{type(error).__name__}: {error}",
            )
            return False
        self._update_artifact(job, artifact, state="ready")
        return True

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        scope_id = str(job["scope_id"])
        lock_path = self.locks_directory / f"{scope_id}.lock"
        try:
            with file_lock(lock_path, timeout_seconds=1800):
                job["state"] = "running"
                job["current_stage"] = "parcels"
                job["progress"] = 0.02
                self._write(job)

                target = job["target"]
                refresh = bool(job.get("refresh", False))
                if target["type"] == "zone":
                    parcel_builder = lambda: self.parcel_service.build_zone(
                        zone_id=str(target["zone_id"]),
                        refresh=refresh,
                    )
                else:
                    parcel_builder = lambda: self.parcel_service.build_bbox(
                        west=float(target["west"]),
                        south=float(target["south"]),
                        east=float(target["east"]),
                        north=float(target["north"]),
                        scope_name=target.get("scope_name"),
                        refresh=refresh,
                    )

                parcel_ok = self._run_builder(
                    job,
                    "parcels",
                    progress=0.05,
                    builder=parcel_builder,
                )
                if not parcel_ok:
                    job["state"] = "failed"
                    job["current_stage"] = "failed"
                    job["progress"] = 1.0
                    job["error"] = job["artifacts"]["parcels"]["error"]
                    self._write(job)
                    return

                optional_builders: list[tuple[str, float, Callable[[], Any]]] = [
                    (
                        "envelopes",
                        0.35,
                        lambda: self.envelope_service.build(
                            scope_id=scope_id,
                            refresh=refresh,
                        ),
                    ),
                    (
                        "grid",
                        0.62,
                        lambda: self.grid_service.build(
                            scope_id=scope_id,
                            refresh=refresh,
                        ),
                    ),
                    (
                        "planning",
                        0.82,
                        lambda: self.planning_service.build(
                            scope_id=scope_id,
                            refresh=refresh,
                        ),
                    ),
                ]

                optional_results = [
                    self._run_builder(
                        job,
                        name,
                        progress=progress,
                        builder=builder,
                    )
                    for name, progress, builder in optional_builders
                ]

                failed_optional = [
                    name
                    for name in ("envelopes", "grid", "planning")
                    if job["artifacts"][name]["state"] == "failed"
                ]
                job["warnings"] = [
                    f"{name} evidence is unavailable; other completed domains remain usable."
                    for name in failed_optional
                ]
                job["state"] = "completed" if all(optional_results) else "partial_failure"
                job["current_stage"] = "complete"
                job["progress"] = 1.0
                self._write(job)
        except Exception as error:  # noqa: BLE001
            job["state"] = "failed"
            job["current_stage"] = "failed"
            job["progress"] = 1.0
            job["error"] = f"{type(error).__name__}: {error}"
            self._write(job)
        finally:
            with self._mutex:
                if self._active_scope_jobs.get(scope_id) == job_id:
                    self._active_scope_jobs.pop(scope_id, None)

    def artifact_status(self, scope_id: str) -> dict[str, dict[str, Any]]:
        parcel_paths = parcel_scope_paths(
            config=self.parcel_service.config,
            project_directory=self.parcel_service.project_directory,
            scope_id=scope_id,
        )
        envelope_paths = self.envelope_service._paths(scope_id)
        grid_paths = self.grid_service._paths(scope_id)
        planning_output, planning_manifest = self.planning_service._paths(scope_id)

        readiness = {
            "parcels": parcel_paths.normalized_output.exists()
            and parcel_paths.manifest_output.exists(),
            "envelopes": envelope_paths.output.exists()
            and envelope_paths.manifest.exists(),
            "grid": grid_paths.output.exists() and grid_paths.manifest.exists(),
            "planning": planning_output.exists() and planning_manifest.exists(),
        }
        return {
            name: {
                "state": "ready" if ready else "missing",
                "error": None,
            }
            for name, ready in readiness.items()
        }

    def shutdown(self) -> None:
        self.executor.shutdown(
            wait=False,
            cancel_futures=False,
        )

    def bundle(self, *, scope_id: str, limit: int = 8000) -> dict[str, Any]:
        status = self.artifact_status(scope_id)
        if status["parcels"]["state"] != "ready":
            raise KeyError(scope_id)

        bundle: dict[str, Any] = {
            "scope_id": scope_id,
            "artifacts": status,
            "parcels": self.parcel_service.feature_collection(
                scope_id=scope_id,
                limit=limit,
            ),
            "envelopes": None,
            "constraints": None,
            "grid": None,
            "planning": None,
        }

        readers = {
            "envelopes": lambda: self.envelope_service.feature_collection(
                scope_id=scope_id,
                layer="development_envelopes",
            ),
            "constraints": lambda: self.envelope_service.feature_collection(
                scope_id=scope_id,
                layer="scope_constraints",
            ),
            "grid": lambda: self.grid_service.grid_evidence(scope_id=scope_id),
            "planning": lambda: self.planning_service.overlays(scope_id=scope_id),
        }

        for name, reader in readers.items():
            artifact_name = "envelopes" if name == "constraints" else name
            if status[artifact_name]["state"] != "ready":
                continue
            try:
                bundle[name] = reader()
            except Exception as error:  # noqa: BLE001
                bundle["artifacts"][artifact_name] = {
                    "state": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }

        return bundle
