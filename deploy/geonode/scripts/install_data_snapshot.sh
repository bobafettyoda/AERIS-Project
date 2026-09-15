#!/usr/bin/env bash
set -euo pipefail

ARCHIVE=""
AERIS_ROOT="/opt/aeris"
PROMOTE=0

usage() {
  cat <<'USAGE'
Usage: install_data_snapshot.sh --archive PATH [--promote] [--aeris-root PATH]

Installs a separately prepared AERIS data snapshot. Code deployments never call
this script automatically. --promote atomically replaces only the files carried
by the snapshot, preserving unrelated runtime/scoped data.
USAGE
}

while (($#)); do
  case "$1" in
    --archive)
      ARCHIVE=${2:?Missing value for --archive}
      shift 2
      ;;
    --aeris-root)
      AERIS_ROOT=${2:?Missing value for --aeris-root}
      shift 2
      ;;
    --promote)
      PROMOTE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "Snapshot archive not found: $ARCHIVE" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SHARED_DIR="$AERIS_ROOT/shared"
DATA_DIR="$SHARED_DIR/data"
SNAPSHOT_ROOT="$SHARED_DIR/data-snapshots"
ACTIVE_FILE="$SHARED_DIR/active-data-snapshot.env"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$DATA_DIR" "$SNAPSHOT_ROOT"
tar -xzf "$ARCHIVE" -C "$STAGE"

for required in "$STAGE/snapshot.json" "$STAGE/snapshot-info.txt" "$STAGE/data"; do
  if [[ ! -e "$required" ]]; then
    echo "Snapshot archive is missing: ${required#$STAGE/}" >&2
    exit 1
  fi
done

SNAPSHOT_ID=$(python3 - "$STAGE/snapshot.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
value = payload.get("snapshot_id")
if not isinstance(value, str) or not value or not all(c.isalnum() or c in "._-" for c in value):
    raise SystemExit("Invalid snapshot_id")
print(value)
PY
)

python3 "$SCRIPT_DIR/data_snapshot.py" verify \
  --data-dir "$STAGE/data" \
  --manifest "$STAGE/snapshot.json"

DESTINATION="$SNAPSHOT_ROOT/$SNAPSHOT_ID"
if [[ -e "$DESTINATION" ]]; then
  echo "Data snapshot already exists: $DESTINATION"
  python3 "$SCRIPT_DIR/data_snapshot.py" verify \
    --data-dir "$STAGE/data" \
    --manifest "$DESTINATION/snapshot.json"
else
  mkdir -p "$DESTINATION"
  cp -a "$STAGE/snapshot.json" "$STAGE/snapshot-info.txt" "$DESTINATION/"
  cp -a "$ARCHIVE" "$DESTINATION/archive.tar.gz"
  sha256sum "$DESTINATION/archive.tar.gz" > "$DESTINATION/archive.tar.gz.sha256"
  chmod 0444 "$DESTINATION/snapshot.json" "$DESTINATION/snapshot-info.txt" \
    "$DESTINATION/archive.tar.gz" "$DESTINATION/archive.tar.gz.sha256"
  chmod 0555 "$DESTINATION"
fi

if ((PROMOTE == 0)); then
  echo "Snapshot installed but not promoted: $SNAPSHOT_ID"
  exit 0
fi

printf '%s\n' "=== PROMOTING DATA SNAPSHOT ==="
while IFS= read -r relative; do
  [[ -z "$relative" || "$relative" == \#* ]] && continue
  source="$STAGE/data/$relative"
  [[ -f "$source" ]] || continue
  destination="$DATA_DIR/$relative"
  mkdir -p "$(dirname "$destination")"
  temporary="${destination}.aeris-new-$$"
  cp -a "$source" "$temporary"
  mv -f "$temporary" "$destination"
done < <(python3 - "$STAGE/snapshot.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
for record in payload.get("files", []):
    print(record["path"])
PY
)

python3 "$SCRIPT_DIR/data_snapshot.py" verify \
  --data-dir "$DATA_DIR" \
  --manifest "$DESTINATION/snapshot.json"

MANIFEST_SHA=$(sha256sum "$DESTINATION/snapshot.json" | awk '{print $1}')
TREE_SHA=$(python3 - "$DESTINATION/snapshot.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["tree_sha256"])
PY
)

cat > "$ACTIVE_FILE" <<ENV
AERIS_DATA_SNAPSHOT_ID=$SNAPSHOT_ID
AERIS_DATA_MANIFEST_SHA256=$MANIFEST_SHA
AERIS_DATA_TREE_SHA256=$TREE_SHA
AERIS_DATA_MANIFEST=$DESTINATION/snapshot.json
ENV
chmod 0644 "$ACTIVE_FILE"

DEPLOY_ENV="$SHARED_DIR/aeris.env"
if [[ -f "$DEPLOY_ENV" ]]; then
  python3 - "$DEPLOY_ENV" "$SNAPSHOT_ID" "$MANIFEST_SHA" <<'PYENV'
from pathlib import Path
import sys

path = Path(sys.argv[1])
updates = {
    "AERIS_DATA_SNAPSHOT_ID": sys.argv[2],
    "AERIS_DATA_MANIFEST_SHA256": sys.argv[3],
}
lines = []
seen = set()
for raw in path.read_text(encoding="utf-8").splitlines():
    if "=" in raw:
        key, _ = raw.split("=", 1)
        if key in updates:
            lines.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    lines.append(raw)
for key, value in updates.items():
    if key not in seen:
        lines.append(f"{key}={value}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PYENV
  chmod 0600 "$DEPLOY_ENV"
fi

chown -R 10001:10001 "$DATA_DIR"
chmod -R u+rwX,go+rX "$DATA_DIR"

echo "Promoted AERIS data snapshot: $SNAPSHOT_ID"
