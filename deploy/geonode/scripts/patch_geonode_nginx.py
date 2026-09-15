#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile

BEGIN = "# BEGIN AERIS MANAGED INCLUDE"
END = "# END AERIS MANAGED INCLUDE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert or update the AERIS include inside the GeoNode server block."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--include-path", required=True)
    return parser.parse_args()


def find_matching_brace(text: str, opening: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    in_comment = False

    for index in range(opening, len(text)):
        char = text[index]

        if in_comment:
            if char == "\n":
                in_comment = False
            continue

        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char == "#":
            in_comment = True
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index

    raise RuntimeError("Unbalanced braces in Nginx configuration")


def server_blocks(text: str) -> list[tuple[int, int, int]]:
    blocks: list[tuple[int, int, int]] = []
    for match in re.finditer(r"(?m)^\s*server\s*\{", text):
        opening = text.find("{", match.start(), match.end())
        closing = find_matching_brace(text, opening)
        body = text[opening + 1 : closing]
        lowered = body.lower()

        score = 0
        if re.search(r"\blisten\s+[^;\n]*443\b", lowered):
            score += 120
        if " ssl" in lowered or "ssl_" in lowered:
            score += 40
        if "server_name" in lowered:
            score += 20
        if re.search(r"(?m)^\s*location\s+/\s*\{", body):
            score += 100
        if "proxy_pass" in lowered:
            score += 30
        if "geonode" in lowered or "django" in lowered:
            score += 30
        if re.search(r"\breturn\s+30[1278]\b", lowered) and "proxy_pass" not in lowered:
            score -= 100

        blocks.append((score, match.start(), closing))
    return blocks


def atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(path.stat().st_mode)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    config = Path(args.config).resolve()
    text = config.read_text(encoding="utf-8")

    pattern = re.compile(
        r"(?ms)^(?P<indent>[ \t]*)"
        + re.escape(BEGIN)
        + r".*?^[ \t]*"
        + re.escape(END)
    )

    existing = pattern.search(text)
    if existing:
        indent = existing.group("indent")
        managed = (
            f"{indent}{BEGIN}\n"
            f"{indent}include {args.include_path};\n"
            f"{indent}{END}"
        )
        updated = text[: existing.start()] + managed + text[existing.end() :]
        target_description = "existing managed block"
    else:
        blocks = server_blocks(text)
        if not blocks:
            raise RuntimeError("No Nginx server block was found")
        blocks.sort(key=lambda item: (item[0], item[1]), reverse=True)
        score, _, closing = blocks[0]
        if score <= 0:
            raise RuntimeError(
                "No suitable GeoNode application server block was identified"
            )

        closing_line_start = text.rfind("\n", 0, closing) + 1
        closing_indent = text[closing_line_start:closing]
        child_indent = closing_indent + "    "
        managed = (
            f"{child_indent}{BEGIN}\n"
            f"{child_indent}include {args.include_path};\n"
            f"{child_indent}{END}"
        )
        insertion = "\n" + managed + "\n"
        updated = text[:closing] + insertion + text[closing:]
        target_description = f"server block with score {score}"

    if updated == text:
        print("CHANGED=0")
        print("BACKUP=")
        print(f"TARGET={target_description}")
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = config.with_name(f"{config.name}.aeris-backup-{timestamp}")
    backup.write_text(text, encoding="utf-8")
    backup.chmod(config.stat().st_mode)
    atomic_write(config, updated)

    print("CHANGED=1")
    print(f"BACKUP={backup}")
    print(f"TARGET={target_description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
