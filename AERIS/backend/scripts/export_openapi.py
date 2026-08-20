from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]

if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.main import app


OUTPUT = BACKEND_DIRECTORY / "openapi.json"

OUTPUT.write_text(
    json.dumps(app.openapi(), indent=2) + "\n",
    encoding="utf-8",
)

print(OUTPUT)
