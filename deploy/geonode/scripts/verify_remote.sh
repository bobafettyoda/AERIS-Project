#!/usr/bin/env bash
set -euo pipefail

PUBLIC_ORIGIN=${1:-}
NGINX_CONTAINER=${2:-nginx4geonode_project}
AERIS_ROOT=${3:-/opt/aeris}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

printf '%s\n' "=== RELEASE STATUS ==="
bash "$SCRIPT_DIR/release_status.sh" "$AERIS_ROOT"

printf '\n%s\n' "=== API HEALTH ==="
docker exec -i aeris-api python - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=20) as response:
    print(json.dumps(json.load(response), indent=2))
PY

printf '\n%s\n' "=== FRONTEND HEALTH ==="
docker exec aeris-web wget -qO- http://127.0.0.1/healthz

printf '\n%s\n' "=== NGINX TEST ==="
docker exec "$NGINX_CONTAINER" nginx -t

printf '\n%s\n' "=== DATA SNAPSHOT VERIFY ==="
ACTIVE="$AERIS_ROOT/shared/active-data-snapshot.env"
if [[ -f "$ACTIVE" ]]; then
  DATA_DIR=$(awk -F= '$1 == "AERIS_DATA_DIR" {sub($1 "=", ""); print; exit}' "$AERIS_ROOT/shared/aeris.env")
  MANIFEST=$(awk -F= '$1 == "AERIS_DATA_MANIFEST" {sub($1 "=", ""); print; exit}' "$ACTIVE")
  python3 "$SCRIPT_DIR/data_snapshot.py" verify --data-dir "$DATA_DIR" --manifest "$MANIFEST"
else
  echo "No active snapshot metadata found." >&2
  exit 1
fi

printf '\n%s\n' "=== PRODUCT SMOKE TESTS ==="
HOST_HEADER=$(python3 - "$PUBLIC_ORIGIN" <<'PY'
import sys
from urllib.parse import urlsplit
value=sys.argv[1].strip()
print(urlsplit(value).netloc if value else "localhost")
PY
)
python3 "$SCRIPT_DIR/smoke_test.py" --origin http://127.0.0.1 --host-header "$HOST_HEADER"
