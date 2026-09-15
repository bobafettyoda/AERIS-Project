#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
OUTPUT_DIR=${AERIS_RELEASE_OUTPUT_DIR:-/mnt/c/Users/faris/Downloads}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

for command_name in npm tar python3 sha256sum; do
  command -v "$command_name" >/dev/null || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done

APP_CONFIG="$REPO_ROOT/AERIS/configs/application.json"
APP_VERSION=$(python3 - "$APP_CONFIG" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("version")
if not isinstance(value, str) or not value:
    raise SystemExit("application.json does not contain a version")
print(value)
PY
)
RELEASE_LABEL=$(python3 - "$APP_CONFIG" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("release_label", "unknown"))
PY
)
RELEASE_ID=${AERIS_RELEASE_ID:-aeris-v${APP_VERSION}-$STAMP}
ARCHIVE="$OUTPUT_DIR/$RELEASE_ID.tar.gz"
CHECKSUM="$ARCHIVE.sha256"
mkdir -p "$OUTPUT_DIR"

FRONTEND="$REPO_ROOT/AERIS/frontend"
if [[ ! -f "$FRONTEND/package.json" ]]; then
  echo "AERIS frontend was not found beneath $REPO_ROOT" >&2
  exit 1
fi

printf '%s\n' "=== LOCAL PREFLIGHT ==="
python3 -m compileall -q "$REPO_ROOT/AERIS/backend/app" "$REPO_ROOT/AERIS/backend/analysis"
python3 "$SCRIPT_DIR/data_snapshot.py" --help >/dev/null
python3 "$SCRIPT_DIR/smoke_test.py" --help >/dev/null

printf '\n%s\n' "=== BUILDING PRODUCTION FRONTEND ==="
cd "$FRONTEND"
if [[ ${AERIS_SKIP_FRONTEND_BUILD:-0} == 1 ]]; then
  echo "Using the existing production build in frontend/dist."
elif [[ ${AERIS_SKIP_NPM_CI:-0} == 1 ]]; then
  npm test
  npm run build
else
  npm ci
  npm test
  npm run build
fi

if [[ ${AERIS_SKIP_LINT:-0} != 1 ]]; then
  npm run lint
fi

if [[ ! -f "$FRONTEND/dist/index.html" ]]; then
  echo "Production frontend build did not create dist/index.html" >&2
  exit 1
fi
if ! grep -q '/aeris/assets/' "$FRONTEND/dist/index.html"; then
  echo "dist/index.html does not use the /aeris/ asset base." >&2
  exit 1
fi
if ! grep -R -q '/aeris-api' "$FRONTEND/dist/assets"; then
  echo "The production bundle does not contain /aeris-api." >&2
  exit 1
fi
if grep -R -nE '127\.0\.0\.1:8000|localhost:8000' "$FRONTEND/dist" >/tmp/aeris-local-api.txt; then
  cat /tmp/aeris-local-api.txt >&2
  echo "The production bundle still contains a local backend URL." >&2
  exit 1
fi

printf '\n%s\n' "=== STAGING CODE-ONLY RELEASE ==="
cd "$REPO_ROOT"
tar -cf - \
  --exclude='./.git' \
  --exclude='./AERIS/backend/.venv' \
  --exclude='./AERIS/backend/.env' \
  --exclude='./AERIS/frontend/.env.local' \
  --exclude='./AERIS/frontend/node_modules' \
  --exclude='./AERIS/data' \
  --exclude='**/__pycache__' \
  --exclude='**/*.pyc' \
  --exclude='**/*.pyo' \
  . | tar -C "$STAGE" -xf -

mkdir -p "$STAGE/AERIS/data"
BRANCH=$(git branch --show-current 2>/dev/null || echo unknown)
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)
DIRTY=clean
if [[ -n $(git status --porcelain 2>/dev/null || true) ]]; then
  DIRTY=dirty
fi

cat > "$STAGE/deploy/geonode/release-info.env" <<INFO
AERIS_RELEASE_ID=$RELEASE_ID
AERIS_RELEASE_LABEL=$RELEASE_LABEL
AERIS_APP_VERSION=$APP_VERSION
AERIS_RELEASE_CREATED_UTC=$STAMP
AERIS_SOURCE_BRANCH=$BRANCH
AERIS_SOURCE_COMMIT=$COMMIT
AERIS_SOURCE_WORKTREE=$DIRTY
AERIS_RELEASE_DATA_MODE=shared-persistent
INFO

python3 - "$STAGE/deploy/geonode/release-info.env" "$STAGE/deploy/geonode/release-info.json" <<'PY'
import json, sys
values = {}
for raw in open(sys.argv[1], encoding="utf-8"):
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        continue
    key, value = raw.split("=", 1)
    values[key] = value
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(values, handle, indent=2)
    handle.write("\n")
PY

cat > "$STAGE/AERIS/frontend/dist/release.json" <<JSON
{
  "release_id": "$RELEASE_ID",
  "release_label": "$RELEASE_LABEL",
  "app_version": "$APP_VERSION",
  "created_utc": "$STAMP",
  "source_commit": "$COMMIT",
  "data_mode": "shared-persistent"
}
JSON

printf '\n%s\n' "=== CREATING RELEASE ARCHIVE ==="
tar -C "$STAGE" -czf "$ARCHIVE" .
sha256sum "$ARCHIVE" > "$CHECKSUM"
cp "$REPO_ROOT/deploy/geonode/deploy-to-geonode.ps1" "$OUTPUT_DIR/"

printf '\n%s\n' "=== RELEASE READY ==="
echo "Release:   $RELEASE_ID"
echo "Archive:   $ARCHIVE"
echo "Checksum:  $CHECKSUM"
echo "Data:      EXCLUDED (uses persistent /opt/aeris/shared/data)"
echo "Rollback:  automatic on smoke-test failure; manual helper included"
cat "$CHECKSUM"
