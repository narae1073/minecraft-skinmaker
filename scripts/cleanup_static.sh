#!/usr/bin/env bash
# Delete generated skins/steps older than SKINMAKER_RETENTION_DAYS (default 14).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAYS="${SKINMAKER_RETENTION_DAYS:-14}"

if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "invalid SKINMAKER_RETENTION_DAYS: $DAYS" >&2
  exit 2
fi
if [ "$DAYS" -lt 1 ]; then
  echo "retention disabled (SKINMAKER_RETENTION_DAYS=$DAYS)"
  exit 0
fi

for sub in skins steps; do
  dir="$ROOT/backend/static/$sub"
  [ -d "$dir" ] || continue
  before="$(find "$dir" -type f | wc -l)"
  find "$dir" -type f \( -name '*.png' -o -name '*.part' \) -mtime +"$DAYS" -delete
  after="$(find "$dir" -type f | wc -l)"
  echo "$sub: removed $(( before - after )) file(s) older than ${DAYS}d (remaining $after)"
done
