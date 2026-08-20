from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
FRONTEND_DIRECTORY = BACKEND_DIRECTORY.parent / "frontend"
OPENAPI_PATH = BACKEND_DIRECTORY / "openapi.json"
OUTPUT_PATH = FRONTEND_DIRECTORY / "src" / "generated" / "api.ts"


def type_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def ts_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    if "$ref" in schema:
        return type_name(str(schema["$ref"]))
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        values = schema["enum"]
        return " | ".join(json.dumps(value) for value in values) or "never"
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " | ".join(ts_type(item) for item in schema[key])
    if "allOf" in schema:
        return " & ".join(ts_type(item) for item in schema["allOf"])

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(
            "null" if value == "null" else ts_type({"type": value})
            for value in schema_type
        )
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        return f"Array<{ts_type(schema.get('items'))}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        lines = ["{"]
        for name, child in properties.items():
            safe_name = name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else json.dumps(name)
            optional = "" if name in required else "?"
            lines.append(f"  {safe_name}{optional}: {ts_type(child)};")
        additional = schema.get("additionalProperties")
        if additional:
            additional_type = "unknown" if additional is True else ts_type(additional)
            lines.append(f"  [key: string]: {additional_type};")
        lines.append("}")
        return "\n".join(lines)
    return "unknown"


def main() -> None:
    if not OPENAPI_PATH.exists():
        raise SystemExit(
            f"OpenAPI document is missing: {OPENAPI_PATH}. Run export_openapi.py first."
        )
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document.get("components", {}).get("schemas", {})
    lines = [
        "// Generated from AERIS/backend/openapi.json. Do not edit manually.",
        "",
    ]
    for name in sorted(schemas):
        lines.append(f"export type {name} = {ts_type(schemas[name])};")
        lines.append("")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
