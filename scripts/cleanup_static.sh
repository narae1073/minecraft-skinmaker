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

# Legacy source photos are no longer created, but remove any that remain
# regardless of age (2026-11-05).
skins_dir="$ROOT/backend/static/skins"
if [ -d "$skins_dir" ]; then
  before="$(find "$skins_dir" -maxdepth 1 -type f -name 'input_*' | wc -l)"
  find "$skins_dir" -maxdepth 1 -type f -name 'input_*' -delete
  after="$(find "$skins_dir" -maxdepth 1 -type f -name 'input_*' | wc -l)"
  echo "input_*: removed $(( before - after )) legacy upload(s) (all ages)"
fi

# Per-skin job records (edit state) expire with the generated skins.
jobs_dir="$ROOT/backend/private/jobs"
if [ -d "$jobs_dir" ]; then
  before="$(find "$jobs_dir" -type f | wc -l)"
  find "$jobs_dir" -type f -mtime +"$DAYS" -delete
  after="$(find "$jobs_dir" -type f | wc -l)"
  echo "private/jobs: removed $(( before - after )) file(s) older than ${DAYS}d (remaining $after)"
fi
