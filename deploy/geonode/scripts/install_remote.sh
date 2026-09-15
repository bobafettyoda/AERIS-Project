#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=""
NGINX_CONTAINER="nginx4geonode_project"
NGINX_CONFIG="/var/lib/docker/volumes/geonode_project-nginxconfd/_data/sites-enabled/geonode.conf"
PUBLIC_ORIGIN=""
AERIS_ROOT="/opt/aeris"
MIN_FREE_GB=${AERIS_MIN_FREE_GB:-2}

usage() {
  cat <<'USAGE'
Usage: install_remote.sh --source-dir PATH [options]

Options:
  --nginx-container NAME   GeoNode Nginx container name
  --nginx-config PATH      Host path to the live GeoNode Nginx config
  --public-origin URL      Public GeoNode origin, such as http://40.76.136.89
  --aeris-root PATH        Persistent installation root (default /opt/aeris)

The installer is code-only. Existing GIS data is adopted into
/opt/aeris/shared/data on the first v0.8 deployment and is never copied from a
normal code release. Candidate images and all three product modules are smoke-
tested before the release is marked current. Post-cutover failure triggers an
automatic rollback.
USAGE
}

while (($#)); do
  case "$1" in
    --source-dir) SOURCE_DIR=${2:?Missing value for --source-dir}; shift 2 ;;
    --nginx-container) NGINX_CONTAINER=${2:?Missing value for --nginx-container}; shift 2 ;;
    --nginx-config) NGINX_CONFIG=${2:?Missing value for --nginx-config}; shift 2 ;;
    --public-origin) PUBLIC_ORIGIN=${2:?Missing value for --public-origin}; shift 2 ;;
    --aeris-root) AERIS_ROOT=${2:?Missing value for --aeris-root}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$SOURCE_DIR" ]]; then
  echo "--source-dir is required" >&2
  exit 2
fi
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

SOURCE_DIR=$(readlink -f "$SOURCE_DIR")
NGINX_CONFIG=$(readlink -f "$NGINX_CONFIG")
SCRIPT_DIR="$SOURCE_DIR/deploy/geonode/scripts"
REQUIRED_FILE="$SOURCE_DIR/deploy/geonode/data-required.txt"
RELEASE_INFO="$SOURCE_DIR/deploy/geonode/release-info.env"

for required in \
  "$SOURCE_DIR/AERIS/backend/app/main.py" \
  "$SOURCE_DIR/AERIS/frontend/dist/index.html" \
  "$SOURCE_DIR/deploy/geonode/docker-compose.yml" \
  "$SCRIPT_DIR/data_snapshot.py" \
  "$SCRIPT_DIR/smoke_test.py" \
  "$REQUIRED_FILE" \
  "$RELEASE_INFO" \
  "$NGINX_CONFIG"
do
  if [[ ! -e "$required" ]]; then
    echo "Required deployment input is missing: $required" >&2
    exit 1
  fi
done

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "Host Python 3 is required." >&2; exit 1; }
command -v tar >/dev/null || { echo "tar is required." >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "sha256sum is required." >&2; exit 1; }

# Require Compose v2. Compose v1 caused the ContainerConfig failure that this
# release process is specifically designed to avoid.
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (docker compose)." >&2
  exit 1
fi
COMPOSE=(docker compose)

read_release_value() {
  local key=$1
  awk -F= -v key="$key" '$1 == key {sub($1 "=", ""); print; exit}' "$RELEASE_INFO"
}

RELEASE_ID=$(read_release_value AERIS_RELEASE_ID)
RELEASE_LABEL=$(read_release_value AERIS_RELEASE_LABEL)
if [[ -z "$RELEASE_ID" || ! "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid or missing AERIS_RELEASE_ID in $RELEASE_INFO" >&2
  exit 1
fi

if ! docker inspect "$NGINX_CONTAINER" >/dev/null 2>&1; then
  echo "GeoNode Nginx container was not found: $NGINX_CONTAINER" >&2
  exit 1
fi

mapfile -t NETWORKS < <(
  docker inspect \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    "$NGINX_CONTAINER" \
    | awk 'NF && $1 != "bridge" && $1 != "host" && $1 != "none"'
)
if ((${#NETWORKS[@]} == 0)); then
  echo "No user-defined network is attached to $NGINX_CONTAINER" >&2
  exit 1
fi
GEONODE_NETWORK=${NETWORKS[0]}

RELEASES_DIR="$AERIS_ROOT/releases"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
SHARED_DIR="$AERIS_ROOT/shared"
DATA_DIR="$SHARED_DIR/data"
SNAPSHOT_ROOT="$SHARED_DIR/data-snapshots"
ACTIVE_SNAPSHOT_FILE="$SHARED_DIR/active-data-snapshot.env"
ENV_FILE="$SHARED_DIR/aeris.env"
ACTIVE_RELEASE_FILE="$SHARED_DIR/active-release.env"
CURRENT_LINK="$AERIS_ROOT/current"
PREVIOUS_LINK="$AERIS_ROOT/previous"

mkdir -p "$RELEASES_DIR" "$SHARED_DIR" "$SNAPSHOT_ROOT"

free_bytes=$(df -PB1 "$AERIS_ROOT" | awk 'NR==2 {print $4}')
minimum_bytes=$((MIN_FREE_GB * 1024 * 1024 * 1024))
if ((free_bytes < minimum_bytes)); then
  echo "Insufficient free disk space under $AERIS_ROOT." >&2
  echo "Free bytes: $free_bytes; required minimum: $minimum_bytes" >&2
  exit 1
fi

validate_required_data() {
  local root=$1
  local missing=0
  while IFS= read -r relative; do
    [[ -z "$relative" || "$relative" == \#* ]] && continue
    if [[ ! -f "$root/$relative" ]]; then
      echo "Missing required data: $root/$relative" >&2
      missing=1
    fi
  done < "$REQUIRED_FILE"
  ((missing == 0))
}

current_data_mount() {
  docker inspect aeris-api \
    --format '{{range .Mounts}}{{if eq .Destination "/opt/aeris/AERIS/data"}}{{println .Source}}{{end}}{{end}}' \
    2>/dev/null | head -n 1 || true
}

DATA_SOURCE=""
MIGRATE_DATA=0
if [[ -d "$DATA_DIR" ]] && validate_required_data "$DATA_DIR"; then
  DATA_SOURCE="$DATA_DIR"
else
  EXISTING_MOUNT=$(current_data_mount)
  if [[ -n "$EXISTING_MOUNT" && -d "$EXISTING_MOUNT" ]] && validate_required_data "$EXISTING_MOUNT"; then
    DATA_SOURCE=$(readlink -f "$EXISTING_MOUNT")
    MIGRATE_DATA=1
    echo "Existing AERIS data will be adopted from: $DATA_SOURCE"
  else
    echo "No valid persistent or currently-mounted AERIS data set was found." >&2
    echo "Normal code deployments do not contain GIS data." >&2
    echo "Install/promote a data snapshot first, or restore the previous AERIS data mount." >&2
    exit 1
  fi
fi

PREVIOUS_RELEASE=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_RELEASE=$(readlink -f "$CURRENT_LINK" || true)
elif [[ "$DATA_SOURCE" == "$RELEASES_DIR"/*/AERIS/data ]]; then
  candidate=${DATA_SOURCE%/AERIS/data}
  if [[ -f "$candidate/deploy/geonode/docker-compose.yml" ]]; then
    PREVIOUS_RELEASE=$candidate
  fi
fi

OLD_API_IMAGE=$(docker inspect aeris-api --format '{{.Image}}' 2>/dev/null || true)
OLD_WEB_IMAGE=$(docker inspect aeris-web --format '{{.Image}}' 2>/dev/null || true)

if [[ -e "$RELEASE_DIR" ]]; then
  echo "Release already exists: $RELEASE_DIR" >&2
  exit 1
fi
cp -a "$SOURCE_DIR" "$RELEASE_DIR"
COMPOSE_FILE="$RELEASE_DIR/deploy/geonode/docker-compose.yml"

snapshot_value() {
  local key=$1
  [[ -f "$ACTIVE_SNAPSHOT_FILE" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub($1 "=", ""); print; exit}' "$ACTIVE_SNAPSHOT_FILE"
}

DATA_SNAPSHOT_ID=""
DATA_MANIFEST_SHA=""
DATA_MANIFEST=""

if [[ "$DATA_SOURCE" == "$DATA_DIR" && -f "$ACTIVE_SNAPSHOT_FILE" ]]; then
  DATA_SNAPSHOT_ID=$(snapshot_value AERIS_DATA_SNAPSHOT_ID)
  DATA_MANIFEST_SHA=$(snapshot_value AERIS_DATA_MANIFEST_SHA256)
  DATA_MANIFEST=$(snapshot_value AERIS_DATA_MANIFEST)
  if [[ -z "$DATA_SNAPSHOT_ID" || -z "$DATA_MANIFEST" || ! -f "$DATA_MANIFEST" ]]; then
    echo "Active data snapshot metadata is incomplete." >&2
    rm -rf "$RELEASE_DIR"
    exit 1
  fi
  python3 "$SCRIPT_DIR/data_snapshot.py" verify \
    --data-dir "$DATA_SOURCE" \
    --manifest "$DATA_MANIFEST"
else
  SNAPSHOT_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  DATA_SNAPSHOT_ID="baseline-$SNAPSHOT_STAMP"
  TEMP_SNAPSHOT=$(mktemp -d)
  trap 'rm -rf "${TEMP_SNAPSHOT:-}"' EXIT
  python3 "$SCRIPT_DIR/data_snapshot.py" create \
    --data-dir "$DATA_SOURCE" \
    --required-file "$REQUIRED_FILE" \
    --snapshot-id "$DATA_SNAPSHOT_ID" \
    --manifest-out "$TEMP_SNAPSHOT/snapshot.json" \
    --source-release "$RELEASE_LABEL"

  SNAPSHOT_DIR="$SNAPSHOT_ROOT/$DATA_SNAPSHOT_ID"
  mkdir -p "$SNAPSHOT_DIR"
  cp "$TEMP_SNAPSHOT/snapshot.json" "$SNAPSHOT_DIR/snapshot.json"
  grep -vE '^\s*(#|$)' "$REQUIRED_FILE" > "$TEMP_SNAPSHOT/files.txt"
  tar -C "$DATA_SOURCE" -czf "$SNAPSHOT_DIR/required-data.tar.gz" -T "$TEMP_SNAPSHOT/files.txt"
  sha256sum "$SNAPSHOT_DIR/required-data.tar.gz" > "$SNAPSHOT_DIR/required-data.tar.gz.sha256"
  DATA_MANIFEST="$SNAPSHOT_DIR/snapshot.json"
  DATA_MANIFEST_SHA=$(sha256sum "$DATA_MANIFEST" | awk '{print $1}')
  chmod 0444 "$SNAPSHOT_DIR"/*
  chmod 0555 "$SNAPSHOT_DIR"
  rm -rf "$TEMP_SNAPSHOT"
  trap - EXIT
fi

export GEONODE_NETWORK
export AERIS_DATA_DIR="$DATA_SOURCE"
export AERIS_PUBLIC_ORIGIN="$PUBLIC_ORIGIN"
export AERIS_RELEASE_ID="$RELEASE_ID"
export AERIS_DATA_SNAPSHOT_ID="$DATA_SNAPSHOT_ID"
export AERIS_DATA_MANIFEST_SHA256="$DATA_MANIFEST_SHA"

printf '%s\n' "=== AERIS v0.8 RELEASE PREFLIGHT ==="
echo "Candidate release: $RELEASE_ID"
echo "Previous release:  ${PREVIOUS_RELEASE:-unmanaged/current runtime}"
echo "Data source:       $DATA_SOURCE"
echo "Data snapshot:     $DATA_SNAPSHOT_ID"
echo "GeoNode network:   $GEONODE_NETWORK"
echo "Free disk:         $free_bytes bytes"

printf '\n%s\n' "=== BUILDING VERSIONED CANDIDATE IMAGES ==="
"${COMPOSE[@]}" -p aeris -f "$COMPOSE_FILE" build --pull

wait_for_http_in_api() {
  local container=$1
  local state=""

  for attempt in $(seq 1 90); do
    state=$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)

    if [[ "$state" == "exited" || "$state" == "dead" ]]; then
      echo "$container stopped during startup." >&2
      docker logs --tail 200 "$container" || true
      return 1
    fi

    if docker exec "$container" python -c \
      'import json, urllib.request; p=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)); assert p.get("ok") is True' \
      >/dev/null 2>&1
    then
      echo "$container API ready."
      return 0
    fi

    printf '%s API starting... (%d/90)\n' "$container" "$attempt"
    sleep 2
  done

  echo "$container did not become ready in time." >&2
  docker logs --tail 200 "$container" || true
  return 1
}

printf '\n%s\n' "=== CANDIDATE SMOKE TEST (NO CUTOVER YET) ==="
SAFE_ID=$(printf '%s' "$RELEASE_ID" | tr -c 'A-Za-z0-9_.-' '-')
CANDIDATE_API="aeris-preflight-api-$SAFE_ID"
CANDIDATE_WEB="aeris-preflight-web-$SAFE_ID"
docker rm -f "$CANDIDATE_API" "$CANDIDATE_WEB" >/dev/null 2>&1 || true
cleanup_candidates() {
  docker rm -f "$CANDIDATE_API" "$CANDIDATE_WEB" >/dev/null 2>&1 || true
}
trap cleanup_candidates EXIT

docker run -d \
  --name "$CANDIDATE_API" \
  --network "$GEONODE_NETWORK" \
  -e AERIS_PROJECT_ROOT=/opt/aeris/AERIS \
  -e "AERIS_CORS_ORIGINS=$PUBLIC_ORIGIN" \
  -e "AERIS_DEPLOYMENT_RELEASE_ID=$RELEASE_ID" \
  -e "AERIS_DATA_SNAPSHOT_ID=$DATA_SNAPSHOT_ID" \
  -e "AERIS_DATA_MANIFEST_SHA256=$DATA_MANIFEST_SHA" \
  -v "$DATA_SOURCE:/opt/aeris/AERIS/data" \
  "aeris/api:$RELEASE_ID" >/dev/null

wait_for_http_in_api "$CANDIDATE_API"
docker cp "$SCRIPT_DIR/smoke_test.py" "$CANDIDATE_API:/tmp/aeris-smoke-test.py" >/dev/null
docker exec "$CANDIDATE_API" python /tmp/aeris-smoke-test.py \
  --origin http://127.0.0.1:8000 \
  --api-prefix '' \
  --skip-frontend

docker run -d \
  --name "$CANDIDATE_WEB" \
  --network "$GEONODE_NETWORK" \
  "aeris/web:$RELEASE_ID" >/dev/null
for attempt in $(seq 1 30); do
  if docker exec "$CANDIDATE_WEB" wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1; then
    break
  fi
  if ((attempt == 30)); then
    docker logs --tail 100 "$CANDIDATE_WEB" || true
    exit 1
  fi
  sleep 1
done
cleanup_candidates
trap - EXIT

echo "Candidate passed pre-cutover smoke tests."

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

rollback_runtime() {
  echo "=== AUTOMATIC ROLLBACK ===" >&2
  remove_runtime_containers

  local rollback_data="$DATA_DIR"
  if ! validate_required_data "$rollback_data" >/dev/null 2>&1; then
    rollback_data="$DATA_SOURCE"
  fi

  if [[ -n "$PREVIOUS_RELEASE" && -f "$PREVIOUS_RELEASE/deploy/geonode/docker-compose.yml" ]]; then
    local previous_compose="$PREVIOUS_RELEASE/deploy/geonode/docker-compose.yml"
    local previous_id=""
    if [[ -f "$PREVIOUS_RELEASE/deploy/geonode/release-info.env" ]]; then
      previous_id=$(awk -F= '$1 == "AERIS_RELEASE_ID" {sub($1 "=", ""); print; exit}' \
        "$PREVIOUS_RELEASE/deploy/geonode/release-info.env")
    elif [[ -f "$PREVIOUS_RELEASE/deploy/geonode/release-info.txt" ]]; then
      previous_id=$(awk -F= '$1 == "release_id" {print $2; exit}' \
        "$PREVIOUS_RELEASE/deploy/geonode/release-info.txt")
    fi
    export AERIS_RELEASE_ID=${previous_id:-previous}
    export AERIS_DATA_DIR="$rollback_data"
    export AERIS_DATA_SNAPSHOT_ID="$DATA_SNAPSHOT_ID"
    export AERIS_DATA_MANIFEST_SHA256="$DATA_MANIFEST_SHA"
    if ! "${COMPOSE[@]}" -p aeris -f "$previous_compose" up -d --no-build --remove-orphans; then
      "${COMPOSE[@]}" -p aeris -f "$previous_compose" up -d --build --remove-orphans
    fi
    ln -sfn "$PREVIOUS_RELEASE" "$CURRENT_LINK"
  elif [[ -n "$OLD_API_IMAGE" && -n "$OLD_WEB_IMAGE" ]]; then
    docker run -d --name aeris-api --restart unless-stopped \
      --network "$GEONODE_NETWORK" \
      -e AERIS_PROJECT_ROOT=/opt/aeris/AERIS \
      -e "AERIS_CORS_ORIGINS=$PUBLIC_ORIGIN" \
      -v "$rollback_data:/opt/aeris/AERIS/data" \
      "$OLD_API_IMAGE" >/dev/null
    docker run -d --name aeris-web --restart unless-stopped \
      --network "$GEONODE_NETWORK" "$OLD_WEB_IMAGE" >/dev/null
  else
    echo "No managed previous release or previous image IDs were available." >&2
    return 1
  fi
  docker exec "$NGINX_CONTAINER" nginx -s reload >/dev/null 2>&1 || true
  echo "Rollback completed." >&2
}

validate_geonode_nginx_routes() {
  local dump
  local missing=0
  dump=$(mktemp)

  if ! docker exec "$NGINX_CONTAINER" nginx -T >"$dump" 2>&1; then
    cat "$dump" >&2
    rm -f "$dump"
    return 1
  fi

  for expected in \
    "location /aeris/" \
    "aeris-web:80" \
    "location /aeris-api/" \
    "aeris-api:8000"
  do
    if ! grep -Fq "$expected" "$dump"; then
      echo "Missing required GeoNode Nginx route fragment: $expected" >&2
      missing=1
    fi
  done

  rm -f "$dump"
  ((missing == 0))
}

printf '\n%s\n' "=== NGINX ROUTE PREFLIGHT ==="
if ! validate_geonode_nginx_routes; then
  echo "Existing GeoNode AERIS routes were not found; refusing cutover." >&2
  echo "The currently running AERIS containers have not been touched." >&2
  exit 1
fi

echo "Existing AERIS routes verified."
echo "Normal AERIS code releases will preserve the GeoNode Nginx configuration."

CUTOVER_STARTED=0

on_deploy_error() {
  local rc=$?
  trap - ERR

  if ((CUTOVER_STARTED == 1)); then
    echo "Unexpected post-cutover failure detected." >&2
    rollback_runtime || true
  fi

  exit "$rc"
}

trap on_deploy_error ERR

printf '\n%s\n' "=== CUTOVER ==="
CUTOVER_STARTED=1
# Stop/remove the current runtime only after the candidate has passed its tests.
remove_runtime_containers

if ((MIGRATE_DATA == 1)); then
  if [[ -e "$DATA_DIR" ]]; then
    if find "$DATA_DIR" -mindepth 1 -print -quit | grep -q .; then
      echo "Shared data target is not empty; refusing to overwrite it." >&2
      rollback_runtime || true
      exit 1
    fi
    rmdir "$DATA_DIR" 2>/dev/null || true
  fi
  mkdir -p "$SHARED_DIR"
  if ! mv "$DATA_SOURCE" "$DATA_DIR"; then
    echo "Failed to move existing AERIS data into shared storage." >&2
    rollback_runtime || true
    exit 1
  fi
  DATA_SOURCE="$DATA_DIR"
  export AERIS_DATA_DIR="$DATA_DIR"
  echo "Existing data moved into persistent shared storage without re-downloading."
fi

chown -R 10001:10001 "$DATA_DIR"
chmod -R u+rwX,go+rX "$DATA_DIR"

cat > "$ACTIVE_SNAPSHOT_FILE" <<ENV
AERIS_DATA_SNAPSHOT_ID=$DATA_SNAPSHOT_ID
AERIS_DATA_MANIFEST_SHA256=$DATA_MANIFEST_SHA
AERIS_DATA_MANIFEST=$DATA_MANIFEST
ENV
chmod 0644 "$ACTIVE_SNAPSHOT_FILE"

cat > "$ENV_FILE" <<ENV
GEONODE_NETWORK=$GEONODE_NETWORK
AERIS_DATA_DIR=$DATA_DIR
AERIS_PUBLIC_ORIGIN=$PUBLIC_ORIGIN
AERIS_RELEASE_ID=$RELEASE_ID
AERIS_DATA_SNAPSHOT_ID=$DATA_SNAPSHOT_ID
AERIS_DATA_MANIFEST_SHA256=$DATA_MANIFEST_SHA
ENV
chmod 0600 "$ENV_FILE"

export AERIS_DATA_DIR="$DATA_DIR"
if ! "${COMPOSE[@]}" -p aeris -f "$COMPOSE_FILE" up -d --no-build --remove-orphans; then
  rollback_runtime || true
  exit 1
fi

wait_for_container_health() {
  local container=$1
  local attempts=${2:-90}
  local state=""
  for attempt in $(seq 1 "$attempts"); do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$container" 2>/dev/null || true)
    printf '%s: %s (%d/%d)\n' "$container" "${state:-missing}" "$attempt" "$attempts"
    if [[ "$state" == "healthy" || "$state" == "running" ]]; then
      return 0
    fi
    if [[ "$state" == "unhealthy" || "$state" == "exited" || "$state" == "dead" ]]; then
      docker logs --tail 200 "$container" || true
      return 1
    fi
    sleep 3
  done
  return 1
}

if ! wait_for_container_health aeris-api 120 || ! wait_for_container_health aeris-web 60; then
  rollback_runtime || true
  exit 1
fi

printf '\n%s\n' "=== GEONODE NGINX ==="

if ! docker exec "$NGINX_CONTAINER" nginx -t; then
  rollback_runtime || true
  exit 1
fi

if ! docker exec "$NGINX_CONTAINER" nginx -s reload; then
  rollback_runtime || true
  exit 1
fi

echo "Existing GeoNode AERIS routes preserved."
echo "Nginx reloaded against the new AERIS containers."

printf '\n%s\n' "=== POST-DEPLOYMENT PRODUCT SMOKE TESTS ==="
HOST_HEADER=$(python3 - "$PUBLIC_ORIGIN" <<'PY'
import sys
from urllib.parse import urlsplit
value = sys.argv[1].strip()
print(urlsplit(value).netloc if value else "localhost")
PY
)
if ! python3 "$SCRIPT_DIR/smoke_test.py" \
  --origin http://127.0.0.1 \
  --host-header "$HOST_HEADER"; then
  rollback_runtime || true
  exit 1
fi

# Only now does the candidate become the active/current release.
if [[ -n "$PREVIOUS_RELEASE" && -d "$PREVIOUS_RELEASE" && "$PREVIOUS_RELEASE" != "$RELEASE_DIR" ]]; then
  ln -sfn "$PREVIOUS_RELEASE" "$PREVIOUS_LINK"
fi
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

cat > "$ACTIVE_RELEASE_FILE" <<ENV
AERIS_RELEASE_ID=$RELEASE_ID
AERIS_RELEASE_DIR=$RELEASE_DIR
AERIS_RELEASE_LABEL=$RELEASE_LABEL
AERIS_DATA_SNAPSHOT_ID=$DATA_SNAPSHOT_ID
AERIS_DATA_MANIFEST_SHA256=$DATA_MANIFEST_SHA
ENV
chmod 0644 "$ACTIVE_RELEASE_FILE"

# Retain the newest five release directories, never deleting current/previous.
mapfile -t OLD_RELEASES < <(
  find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -nr | tail -n +6 | cut -d' ' -f2-
)
for old_release in "${OLD_RELEASES[@]}"; do
  [[ "$old_release" == "$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)" ]] && continue
  [[ "$old_release" == "$(readlink -f "$PREVIOUS_LINK" 2>/dev/null || true)" ]] && continue
  rm -rf "$old_release"
done

# Keep versioned images only for retained release directories. This prevents the
# VM from slowly filling while preserving exact rollback images.
for repository in aeris/api aeris/web; do
  while IFS= read -r image; do
    [[ -z "$image" ]] && continue
    tag=${image#${repository}:}
    if [[ "$tag" != "$image" && ! -d "$RELEASES_DIR/$tag" ]]; then
      docker image rm "$image" >/dev/null 2>&1 || true
    fi
  done < <(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "^${repository}:" || true)
done
docker image prune -f >/dev/null 2>&1 || true

CUTOVER_STARTED=0
trap - ERR

printf '\n%s\n' "=== DEPLOYMENT COMPLETE ==="
echo "Release:       $RELEASE_ID"
echo "Current:       $CURRENT_LINK -> $RELEASE_DIR"
echo "Persistent data: $DATA_DIR"
echo "Data snapshot: $DATA_SNAPSHOT_ID"
echo "Rollback:      sudo $CURRENT_LINK/deploy/geonode/scripts/rollback_remote.sh"
if [[ -n "$PUBLIC_ORIGIN" ]]; then
  echo "AERIS URL:     ${PUBLIC_ORIGIN%/}/aeris/"
  echo "Health URL:    ${PUBLIC_ORIGIN%/}/aeris-api/health"
fi
