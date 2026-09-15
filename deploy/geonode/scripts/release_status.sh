#!/usr/bin/env bash
set -euo pipefail

AERIS_ROOT=${1:-/opt/aeris}
SHARED="$AERIS_ROOT/shared"

value() {
  local file=$1 key=$2
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub($1 "=", ""); print; exit}' "$file"
}

CURRENT=$(readlink -f "$AERIS_ROOT/current" 2>/dev/null || true)
PREVIOUS=$(readlink -f "$AERIS_ROOT/previous" 2>/dev/null || true)
RELEASE_ID=$(value "$SHARED/aeris.env" AERIS_RELEASE_ID)
DATA_DIR=$(value "$SHARED/aeris.env" AERIS_DATA_DIR)
SNAPSHOT=$(value "$SHARED/active-data-snapshot.env" AERIS_DATA_SNAPSHOT_ID)
MANIFEST_SHA=$(value "$SHARED/active-data-snapshot.env" AERIS_DATA_MANIFEST_SHA256)
MANIFEST=$(value "$SHARED/active-data-snapshot.env" AERIS_DATA_MANIFEST)

cat <<OUT
AERIS release status
--------------------
Active release:   ${RELEASE_ID:-unknown}
Current path:     ${CURRENT:-unmanaged}
Previous path:    ${PREVIOUS:-none}
Persistent data: ${DATA_DIR:-unknown}
Data snapshot:   ${SNAPSHOT:-unknown}
Manifest SHA256: ${MANIFEST_SHA:-unknown}
Manifest path:   ${MANIFEST:-unknown}
OUT

if docker inspect aeris-api >/dev/null 2>&1; then
  echo
  echo "Containers:"
  docker ps --filter name='^/aeris-' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
fi
