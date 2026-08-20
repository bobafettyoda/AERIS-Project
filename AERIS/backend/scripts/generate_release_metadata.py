from __future__ import annotations

import json
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent
SOURCE = PROJECT_DIRECTORY / "configs" / "application.json"
OUTPUT = PROJECT_DIRECTORY / "frontend" / "src" / "generated" / "release.ts"


def main() -> None:
    metadata = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "// Generated from AERIS/configs/application.json. Do not edit.\n"
        f"export const AERIS_VERSION = {json.dumps(metadata['version'])} as const;\n"
        f"export const AERIS_RELEASE_LABEL = {json.dumps(metadata['release_label'])} as const;\n"
        f"export const AERIS_RELEASE_STAGE = {json.dumps(metadata['release_stage'])} as const;\n"
        f"export const AERIS_SNAPSHOT_CATALOG = {json.dumps(metadata['snapshot_catalog'], indent=2)} as const;\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
