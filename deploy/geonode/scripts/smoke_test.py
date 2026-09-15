#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def request_json(url: str, host_header: str | None, timeout: float) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if host_header:
        headers["Host"] = host_header
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
        return response.status, payload


def request_text(url: str, host_header: str | None, timeout: float) -> tuple[int, str, str]:
    headers = {"Accept": "text/html,*/*"}
    if host_header:
        headers["Host"] = host_header
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, response.headers.get("content-type", ""), body


def api_url(origin: str, path: str, api_prefix: str) -> str:
    return f"{origin.rstrip('/')}{api_prefix}{path}"


def run(args: argparse.Namespace) -> list[CheckResult]:
    origin = args.origin.rstrip("/")
    results: list[CheckResult] = []

    def check(name: str, function) -> None:
        try:
            detail = function()
            results.append(CheckResult(name=name, ok=True, detail=detail))
        except Exception as error:  # noqa: BLE001 - smoke test reports all failures
            results.append(CheckResult(name=name, ok=False, detail=f"{type(error).__name__}: {error}"))

    if not args.skip_frontend:
        def frontend() -> str:
            status, content_type, body = request_text(
                f"{origin}{args.frontend_prefix}/",
                args.host_header,
                args.timeout,
            )
            if status != 200:
                raise AssertionError(f"HTTP {status}")
            if "text/html" not in content_type:
                raise AssertionError(f"unexpected content-type {content_type!r}")
            if 'id="root"' not in body and "id='root'" not in body:
                raise AssertionError("frontend root element is missing")
            return f"HTTP {status}; React root present"

        check("frontend", frontend)

    def health() -> str:
        status, payload = request_json(
            api_url(origin, "/health", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if status != 200 or payload.get("ok") is not True:
            raise AssertionError(f"unexpected health payload: {payload}")
        release = payload.get("deployment_release_id") or payload.get("release_label")
        snapshot = payload.get("data_snapshot_id") or "unreported"
        return f"release={release}; data_snapshot={snapshot}"

    check("api-health", health)

    def site_evaluator() -> str:
        _, validation = request_json(
            api_url(origin, "/analysis/data-center-demo/validate", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if validation.get("valid") is not True:
            raise AssertionError(f"decision model invalid: {validation}")
        total = float(validation.get("weight_total", -1))
        if not math.isclose(total, 1.0, abs_tol=0.001):
            raise AssertionError(f"weight total is {total}")
        _, sample = request_json(
            api_url(origin, "/analysis/data-center-demo/sample-score", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        score = sample.get("suitability_score")
        if not isinstance(score, (int, float)):
            raise AssertionError("sample suitability score is missing")
        return f"model valid; sample_score={float(score):.5f}"

    check("site-evaluator", site_evaluator)

    def statewide() -> str:
        _, health_payload = request_json(
            api_url(origin, "/analysis/statewide/health", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if health_payload.get("ready") is not True:
            raise AssertionError(f"statewide not ready: {health_payload}")
        _, summary = request_json(
            api_url(origin, "/analysis/statewide/summary", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if not isinstance(summary, dict) or not summary:
            raise AssertionError("statewide summary is empty")
        _, grid = request_json(
            api_url(origin, "/analysis/statewide/grid?limit=1", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if grid.get("type") != "FeatureCollection" or not grid.get("features"):
            raise AssertionError("statewide grid did not return a feature")
        _, zones = request_json(
            api_url(origin, "/analysis/statewide/candidate-zones?mode=top&top_n=1", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if zones.get("type") != "FeatureCollection":
            raise AssertionError("candidate zones response is not GeoJSON")
        return f"grid_feature=ok; candidate_zones={len(zones.get('features', []))}"

    check("statewide-screening", statewide)

    def parcels() -> str:
        _, health_payload = request_json(
            api_url(origin, "/analysis/parcels/health", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        if health_payload.get("ready") is not True:
            raise AssertionError(f"parcel service not ready: {health_payload}")
        _, scopes_payload = request_json(
            api_url(origin, "/analysis/parcels/scopes", args.api_prefix),
            args.host_header,
            args.timeout,
        )
        scopes = scopes_payload.get("scopes", [])
        if not isinstance(scopes, list):
            raise AssertionError("parcel scopes is not a list")

        detail = f"service ready; scopes={len(scopes)}"
        if scopes:
            first = scopes[0]
            scope_id: str | None = None
            if isinstance(first, str):
                scope_id = first
            elif isinstance(first, dict):
                scope = first.get("scope")
                if isinstance(scope, dict):
                    value = scope.get("scope_id")
                    if isinstance(value, str):
                        scope_id = value
                if scope_id is None:
                    value = first.get("scope_id")
                    if isinstance(value, str):
                        scope_id = value
            if scope_id:
                encoded = urllib.parse.quote(scope_id, safe="")
                _, bundle = request_json(
                    api_url(
                        origin,
                        f"/analysis/parcels/scopes/{encoded}/bundle?limit=1",
                        args.api_prefix,
                    ),
                    args.host_header,
                    args.timeout,
                )
                parcels_payload = bundle.get("parcels") if isinstance(bundle, dict) else None
                if not isinstance(parcels_payload, dict):
                    raise AssertionError(f"scope {scope_id!r} bundle is missing parcels")
                if parcels_payload.get("type") != "FeatureCollection":
                    raise AssertionError(f"scope {scope_id!r} parcels are not GeoJSON")
                detail += f"; bundle={scope_id}"
        return detail

    check("parcel-investigation", parcels)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the deployed AERIS product workflow.")
    parser.add_argument("--origin", required=True, help="Origin used for requests, e.g. http://127.0.0.1")
    parser.add_argument("--host-header", default=None)
    parser.add_argument("--api-prefix", default="/aeris-api")
    parser.add_argument("--frontend-prefix", default="/aeris")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    results = run(args)
    width = max(len(result.name) for result in results)
    failures = 0
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        if not result.ok:
            failures += 1
        print(f"[{status}] {result.name:<{width}}  {result.detail}")

    print(f"\nAERIS smoke tests: {len(results) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
