#!/usr/bin/env bash
# Remove user source photos and the old photo-bearing steps sheets.
# Result skins are kept. Run once on the release clone after deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --root) ROOT="${2:?--root needs a directory}"; shift ;;
    *) echo "usage: $0 [--root DIR] --yes" >&2; exit 2 ;;
  esac
  shift
done
[ "$YES" = 1 ] || { echo "refusing to delete without --yes" >&2; exit 2; }

SKINS="$ROOT/backend/static/skins"
STEPS="$ROOT/backend/static/steps"
INPUTS="$ROOT/backend/private/inputs"

count_files() { if [ -d "$1" ]; then find "$1" -type f | wc -l; else echo 0; fi; }

before_skins="$(count_files "$SKINS")"
before_steps="$(count_files "$STEPS")"
before_inputs="$(count_files "$INPUTS")"

if [ -d "$SKINS" ]; then
  find "$SKINS" -maxdepth 1 -type f -name 'input_*' -delete
fi
if [ -d "$STEPS" ]; then
  find "$STEPS" -mindepth 1 -type f -delete
fi
if [ -d "$INPUTS" ]; then
  find "$INPUTS" -mindepth 1 -type f -delete
fi

echo "skins: removed $(( before_skins - $(count_files "$SKINS") )) legacy input file(s); $(count_files "$SKINS") result skin(s) kept"
echo "steps: removed $(( before_steps - $(count_files "$STEPS") )) file(s)"
echo "private inputs: removed $(( before_inputs - $(count_files "$INPUTS") )) file(s)"
