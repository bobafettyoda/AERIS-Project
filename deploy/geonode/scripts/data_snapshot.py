#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load_required(path: Path) -> list[str]:
    values: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith("/") or ".." in Path(value).parts:
            raise ValueError(f"Unsafe data path in {path}: {value}")
        values.append(value)
    if not values:
        raise ValueError(f"No required data paths were found in {path}")
    return values


def iter_files(root: Path, required: Iterable[str], include_all: bool) -> list[Path]:
    if include_all:
        ignored_top = {"runtime", "cache"}
        files = [
            path
            for path in root.rglob("*")
            if path.is_file()
            and not any(part in ignored_top for part in path.relative_to(root).parts)
            and not path.name.endswith((".part", ".tmp"))
        ]
        return sorted(files, key=lambda value: value.as_posix())

    files = []
    for relative in required:
        candidate = root / relative
        if candidate.is_file():
            files.append(candidate)
    return sorted(files, key=lambda value: value.as_posix())


def build_manifest(
    data_dir: Path,
    required_file: Path,
    snapshot_id: str,
    include_all: bool,
    source_release: str | None,
    source_commit: str | None,
) -> dict[str, object]:
    data_dir = data_dir.resolve()
    required = load_required(required_file)

    missing = [relative for relative in required if not (data_dir / relative).is_file()]
    if missing:
        raise FileNotFoundError(
            "Required AERIS data artifacts are missing:\n  - " + "\n  - ".join(missing)
        )

    files = iter_files(data_dir, required, include_all=include_all)
    records: list[dict[str, object]] = []
    tree = hashlib.sha256()
    total_bytes = 0

    for path in files:
        relative = path.relative_to(data_dir).as_posix()
        size = path.stat().st_size
        digest = sha256_file(path)
        total_bytes += size
        tree.update(f"{digest}  {relative}\n".encode("utf-8"))
        records.append({"path": relative, "size_bytes": size, "sha256": digest})

    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "full_without_runtime_cache" if include_all else "required_baseline",
        "source_release": source_release,
        "source_commit": source_commit,
        "required_paths": required,
        "file_count": len(records),
        "total_bytes": total_bytes,
        "tree_sha256": tree.hexdigest(),
        "files": records,
    }


def verify_manifest(data_dir: Path, manifest_path: Path) -> tuple[bool, list[str]]:
    data_dir = data_dir.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version={payload.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        errors.append("manifest does not contain any files")
        return False, errors

    tree = hashlib.sha256()
    for record in files:
        if not isinstance(record, dict):
            errors.append("invalid file record")
            continue
        relative = str(record.get("path", ""))
        expected = str(record.get("sha256", ""))
        expected_size = record.get("size_bytes")
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"unsafe or empty path in manifest: {relative!r}")
            continue
        path = data_dir / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
            continue
        actual_size = path.stat().st_size
        if expected_size != actual_size:
            errors.append(
                f"size mismatch: {relative} expected={expected_size} actual={actual_size}"
            )
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(
                f"sha256 mismatch: {relative} expected={expected} actual={actual}"
            )
            continue
        tree.update(f"{actual}  {relative}\n".encode("utf-8"))

    expected_tree = str(payload.get("tree_sha256", ""))
    if expected_tree and tree.hexdigest() != expected_tree:
        errors.append(
            f"tree sha256 mismatch expected={expected_tree} actual={tree.hexdigest()}"
        )

    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify AERIS data snapshot manifests using only the Python standard library."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--data-dir", required=True)
    create.add_argument("--required-file", required=True)
    create.add_argument("--snapshot-id", required=True)
    create.add_argument("--manifest-out", required=True)
    create.add_argument("--include-all", action="store_true")
    create.add_argument("--source-release", default=os.getenv("AERIS_RELEASE_LABEL"))
    create.add_argument("--source-commit", default=os.getenv("AERIS_SOURCE_COMMIT"))

    verify = sub.add_parser("verify")
    verify.add_argument("--data-dir", required=True)
    verify.add_argument("--manifest", required=True)

    args = parser.parse_args()

    if args.command == "create":
        data_dir = Path(args.data_dir)
        required_file = Path(args.required_file)
        manifest_out = Path(args.manifest_out)
        manifest = build_manifest(
            data_dir=data_dir,
            required_file=required_file,
            snapshot_id=args.snapshot_id,
            include_all=bool(args.include_all),
            source_release=args.source_release,
            source_commit=args.source_commit,
        )
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "snapshot_id": manifest["snapshot_id"],
            "scope": manifest["scope"],
            "file_count": manifest["file_count"],
            "total_bytes": manifest["total_bytes"],
            "tree_sha256": manifest["tree_sha256"],
            "manifest": str(manifest_out),
        }, indent=2))
        return 0

    ok, errors = verify_manifest(Path(args.data_dir), Path(args.manifest))
    if not ok:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    print(json.dumps({
        "ok": True,
        "snapshot_id": payload.get("snapshot_id"),
        "tree_sha256": payload.get("tree_sha256"),
        "file_count": payload.get("file_count"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
