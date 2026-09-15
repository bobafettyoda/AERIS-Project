#!/usr/bin/env bash
set -euo pipefail

AERIS_ROOT="/opt/aeris"
TARGET_RELEASE=""
NGINX_CONTAINER="nginx4geonode_project"
PUBLIC_ORIGIN=""

usage() {
  cat <<'USAGE'
Usage: rollback_remote.sh [--release RELEASE_ID] [--aeris-root PATH] [--public-origin URL]

Without --release, rolls back to /opt/aeris/previous. Persistent GIS data is
never replaced by a code rollback.
USAGE
}

while (($#)); do
  case "$1" in
    --release) TARGET_RELEASE=${2:?Missing value for --release}; shift 2 ;;
    --aeris-root) AERIS_ROOT=${2:?Missing value for --aeris-root}; shift 2 ;;
    --public-origin) PUBLIC_ORIGIN=${2:?Missing value for --public-origin}; shift 2 ;;
    --nginx-container) NGINX_CONTAINER=${2:?Missing value for --nginx-container}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this rollback with sudo." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

SHARED_DIR="$AERIS_ROOT/shared"
ENV_FILE="$SHARED_DIR/aeris.env"
ACTIVE_SNAPSHOT_FILE="$SHARED_DIR/active-data-snapshot.env"
CURRENT_LINK="$AERIS_ROOT/current"
PREVIOUS_LINK="$AERIS_ROOT/previous"
RELEASES_DIR="$AERIS_ROOT/releases"

if [[ -n "$TARGET_RELEASE" ]]; then
  TARGET="$RELEASES_DIR/$TARGET_RELEASE"
else
  if [[ ! -L "$PREVIOUS_LINK" ]]; then
    echo "No previous managed AERIS release exists." >&2
    exit 1
  fi
  TARGET=$(readlink -f "$PREVIOUS_LINK")
fi

if [[ ! -f "$TARGET/deploy/geonode/docker-compose.yml" ]]; then
  echo "Rollback target is not a valid release: $TARGET" >&2
  exit 1
fi

CURRENT=""
if [[ -L "$CURRENT_LINK" ]]; then
  CURRENT=$(readlink -f "$CURRENT_LINK")
fi

read_env_value() {
  local file=$1 key=$2
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub($1 "=", ""); print; exit}' "$file"
}

if [[ -f "$ENV_FILE" ]]; then
  GEONODE_NETWORK=$(read_env_value "$ENV_FILE" GEONODE_NETWORK)
  DATA_DIR=$(read_env_value "$ENV_FILE" AERIS_DATA_DIR)
  [[ -z "$PUBLIC_ORIGIN" ]] && PUBLIC_ORIGIN=$(read_env_value "$ENV_FILE" AERIS_PUBLIC_ORIGIN)
else
  echo "Shared deployment environment is missing: $ENV_FILE" >&2
  exit 1
fi

DATA_SNAPSHOT_ID=$(read_env_value "$ACTIVE_SNAPSHOT_FILE" AERIS_DATA_SNAPSHOT_ID)
DATA_MANIFEST_SHA=$(read_env_value "$ACTIVE_SNAPSHOT_FILE" AERIS_DATA_MANIFEST_SHA256)

TARGET_ID=""
if [[ -f "$TARGET/deploy/geonode/release-info.env" ]]; then
  TARGET_ID=$(read_env_value "$TARGET/deploy/geonode/release-info.env" AERIS_RELEASE_ID)
elif [[ -f "$TARGET/deploy/geonode/release-info.txt" ]]; then
  TARGET_ID=$(awk -F= '$1 == "release_id" {print $2; exit}' "$TARGET/deploy/geonode/release-info.txt")
fi
TARGET_ID=${TARGET_ID:-$(basename "$TARGET")}

export GEONODE_NETWORK
export AERIS_DATA_DIR="$DATA_DIR"
export AERIS_PUBLIC_ORIGIN="$PUBLIC_ORIGIN"
export AERIS_RELEASE_ID="$TARGET_ID"
export AERIS_DATA_SNAPSHOT_ID="$DATA_SNAPSHOT_ID"
export AERIS_DATA_MANIFEST_SHA256="$DATA_MANIFEST_SHA"

remove_runtime_containers() {
  local ids=()
  local id=""
  local name=""

  while read -r id name; do
    if [[ "$name" == "aeris-api" ||
          "$name" == "aeris-web" ||
          "$name" =~ ^[0-9a-f]{12}_aeris-(api|web)$ ]]; then
      ids+=("$id")
    fi
  done < <(docker ps -a --format '{{.ID}} {{.Names}}')

  if ((${#ids[@]})); then
    echo "Removing existing/stale AERIS runtime containers..."
    docker rm -f "${ids[@]}" >/dev/null
  fi
}

printf '%s\n' "=== AERIS ROLLBACK ==="
echo "Current: ${CURRENT:-unknown}"
echo "Target:  $TARGET"
echo "Data:    $DATA_DIR (unchanged)"
echo "Snapshot: ${DATA_SNAPSHOT_ID:-unknown}"

remove_runtime_containers
COMPOSE_FILE="$TARGET/deploy/geonode/docker-compose.yml"
if ! docker compose -p aeris -f "$COMPOSE_FILE" up -d --no-build --remove-orphans; then
  echo "Target images are not available; rebuilding the retained release source." >&2
  docker compose -p aeris -f "$COMPOSE_FILE" up -d --build --remove-orphans
fi

wait_health() {
  local container=$1
  for attempt in $(seq 1 100); do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
    echo "$container: ${state:-missing} ($attempt/100)"
    [[ "$state" == "healthy" || "$state" == "running" ]] && return 0
    [[ "$state" == "unhealthy" || "$state" == "exited" || "$state" == "dead" ]] && return 1
    sleep 3
  done
  return 1
}

wait_health aeris-api
wait_health aeris-web
docker exec "$NGINX_CONTAINER" nginx -t
docker exec "$NGINX_CONTAINER" nginx -s reload

HOST_HEADER=$(python3 - "$PUBLIC_ORIGIN" <<'PY'
import sys
from urllib.parse import urlsplit
value = sys.argv[1].strip()
print(urlsplit(value).netloc if value else "localhost")
PY
)
SMOKE="$TARGET/deploy/geonode/scripts/smoke_test.py"
if [[ -f "$SMOKE" ]]; then
  python3 "$SMOKE" --origin http://127.0.0.1 --host-header "$HOST_HEADER"
else
  python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1/aeris-api/health", timeout=30) as response:
    payload=json.load(response)
    assert payload.get("ok") is True
print("Legacy rollback health check passed.")
PY
fi

if [[ -n "$CURRENT" && -d "$CURRENT" && "$CURRENT" != "$TARGET" ]]; then
  ln -sfn "$CURRENT" "$PREVIOUS_LINK"
fi
ln -sfn "$TARGET" "$CURRENT_LINK"

cat > "$ENV_FILE" <<ENV
GEONODE_NETWORK=$GEONODE_NETWORK
AERIS_DATA_DIR=$DATA_DIR
AERIS_PUBLIC_ORIGIN=$PUBLIC_ORIGIN
AERIS_RELEASE_ID=$TARGET_ID
AERIS_DATA_SNAPSHOT_ID=$DATA_SNAPSHOT_ID
AERIS_DATA_MANIFEST_SHA256=$DATA_MANIFEST_SHA
ENV
chmod 0600 "$ENV_FILE"

echo "Rollback successful: $TARGET_ID"
