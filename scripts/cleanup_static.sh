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

# Original photos and job records (per-skin edit state) are private and expire
# with the skins. Older public input_* photos from before the private store are
# removed too.
for dir in "$ROOT/backend/private/inputs" "$ROOT/backend/private/jobs" "$ROOT/backend/static/skins"; do
  [ -d "$dir" ] || continue
  before="$(find "$dir" -type f | wc -l)"
  if [ "$dir" = "$ROOT/backend/static/skins" ]; then
    find "$dir" -type f -name 'input_*' -mtime +"$DAYS" -delete
  else
    find "$dir" -type f -mtime +"$DAYS" -delete
  fi
  after="$(find "$dir" -type f | wc -l)"
  echo "${dir#$ROOT/}: removed $(( before - after )) file(s) older than ${DAYS}d (remaining $after)"
done
