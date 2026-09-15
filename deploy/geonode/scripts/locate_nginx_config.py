#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map a host-side Nginx configuration path to the "
            "corresponding path inside a running Docker container."
        )
    )
    parser.add_argument("--container", required=True)
    parser.add_argument("--host-path", required=True)
    parser.add_argument(
        "--fallback",
        default="/etc/nginx/sites-enabled/geonode.conf",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    completed = subprocess.run(
        ["docker", "inspect", args.container],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not payload:
        raise RuntimeError(f"Container not found: {args.container}")

    host_path = Path(args.host_path).resolve()
    mounts = payload[0].get("Mounts", [])

    candidates: list[tuple[int, str]] = []
    for mount in mounts:
        source_value = mount.get("Source")
        destination_value = mount.get("Destination")
        if not source_value or not destination_value:
            continue

        source = Path(source_value).resolve()
        try:
            relative = host_path.relative_to(source)
        except ValueError:
            continue

        destination = PurePosixPath(destination_value)
        container_path = str(destination / PurePosixPath(relative.as_posix()))
        candidates.append((len(str(source)), container_path))

    if candidates:
        candidates.sort(reverse=True)
        print(candidates[0][1])
        return 0

    fallback_check = subprocess.run(
        ["docker", "exec", args.container, "test", "-f", args.fallback],
        check=False,
    )
    if fallback_check.returncode == 0:
        print(args.fallback)
        return 0

    print(
        "Unable to map the host Nginx configuration into the container.\n"
        f"Host path: {host_path}\n"
        f"Fallback: {args.fallback}\n"
        "Container mounts:\n"
        + "\n".join(
            f"  {item.get('Source')} -> {item.get('Destination')}"
            for item in mounts
        ),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
