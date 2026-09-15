#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
DATA_DIR=${AERIS_DATA_DIR:-$REPO_ROOT/AERIS/data}
OUTPUT_DIR=${AERIS_DATA_SNAPSHOT_OUTPUT_DIR:-${AERIS_RELEASE_OUTPUT_DIR:-/mnt/c/Users/faris/Downloads}}
MODE=${AERIS_DATA_SNAPSHOT_MODE:-baseline}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_ID=${AERIS_DATA_SNAPSHOT_ID:-md-$STAMP}
SNAPSHOT_DIR=$(mktemp -d)
MANIFEST="$SNAPSHOT_DIR/snapshot.json"
ARCHIVE="$OUTPUT_DIR/aeris-data-$SNAPSHOT_ID.tar.gz"
ARCHIVE_SHA="$ARCHIVE.sha256"
REQUIRED_FILE="$REPO_ROOT/deploy/geonode/data-required.txt"

cleanup() {
  rm -rf "$SNAPSHOT_DIR"
}
trap cleanup EXIT

case "$MODE" in
  baseline|full)
    ;;
  *)
    echo "AERIS_DATA_SNAPSHOT_MODE must be baseline or full." >&2
    exit 2
    ;;
esac

mkdir -p "$OUTPUT_DIR"

for command_name in python3 tar sha256sum; do
  command -v "$command_name" >/dev/null || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done

if [[ ! -d "$DATA_DIR" ]]; then
  echo "AERIS data directory not found: $DATA_DIR" >&2
  exit 1
fi

INCLUDE_ALL=()
if [[ "$MODE" == "full" ]]; then
  INCLUDE_ALL=(--include-all)
fi

BRANCH=$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo unknown)
COMMIT=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)
RELEASE_LABEL=$(python3 - "$REPO_ROOT/AERIS/configs/application.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("release_label", "unknown"))
PY
)

AERIS_RELEASE_LABEL="$RELEASE_LABEL" \
AERIS_SOURCE_COMMIT="$COMMIT" \
python3 "$SCRIPT_DIR/data_snapshot.py" create \
  --data-dir "$DATA_DIR" \
  --required-file "$REQUIRED_FILE" \
  --snapshot-id "$SNAPSHOT_ID" \
  --manifest-out "$MANIFEST" \
  "${INCLUDE_ALL[@]}"

STAGE="$SNAPSHOT_DIR/data"
mkdir -p "$STAGE"

if [[ "$MODE" == "baseline" ]]; then
  while IFS= read -r relative; do
    [[ -z "$relative" || "$relative" == \#* ]] && continue
    mkdir -p "$STAGE/$(dirname "$relative")"
    cp -a "$DATA_DIR/$relative" "$STAGE/$relative"
  done < "$REQUIRED_FILE"
else
  tar -C "$DATA_DIR" \
    --exclude='./runtime' \
    --exclude='./cache' \
    --exclude='*.part' \
    --exclude='*.tmp' \
    -cf - . | tar -C "$STAGE" -xf -
fi

cat > "$SNAPSHOT_DIR/snapshot-info.txt" <<INFO
snapshot_id=$SNAPSHOT_ID
created_utc=$STAMP
mode=$MODE
source_release=$RELEASE_LABEL
source_branch=$BRANCH
source_commit=$COMMIT
INFO

tar -C "$SNAPSHOT_DIR" -czf "$ARCHIVE" snapshot.json snapshot-info.txt data
sha256sum "$ARCHIVE" > "$ARCHIVE_SHA"

printf '\n%s\n' "=== DATA SNAPSHOT READY ==="
echo "Snapshot: $SNAPSHOT_ID"
echo "Mode:     $MODE"
echo "Archive:  $ARCHIVE"
echo "Checksum: $ARCHIVE_SHA"
cat "$ARCHIVE_SHA"
