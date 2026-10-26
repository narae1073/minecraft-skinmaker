#!/usr/bin/env bash
# Prepare a fresh clone or git worktree for development.
#
#   ./scripts/dev_setup.sh              # YuNet only, symlink local assets if possible
#   ./scripts/dev_setup.sh --with-schp  # also fetch the 66 MB parser model
#   ./scripts/dev_setup.sh --with-npm   # force npm ci
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_SCHP=0
WITH_NPM=0
for arg in "$@"; do
  case "$arg" in
    --with-schp) WITH_SCHP=1 ;;
    --with-npm) WITH_NPM=1 ;;
    *) echo "usage: $0 [--with-schp] [--with-npm]" >&2; exit 2 ;;
  esac
done

# First entry of `git worktree list` is the main checkout (same as ROOT in a clone).
MAIN="$(git -C "$ROOT" worktree list --porcelain | awk '/^worktree / {print $2; exit}')"
echo "root: $ROOT"
echo "main: $MAIN"

mkdir -p "$ROOT/out"

link_from_main() {
  local rel="$1"
  if [ ! -e "$ROOT/$rel" ] && [ -e "$MAIN/$rel" ]; then
    mkdir -p "$(dirname "$ROOT/$rel")"
    ln -s "$MAIN/$rel" "$ROOT/$rel"
    echo "link: $rel -> $MAIN/$rel"
  fi
}

if [ "$MAIN" != "$ROOT" ]; then
  link_from_main ".env"
  link_from_main "out/s0_photos"
  link_from_main "out/models"
fi

if [ ! -f "$ROOT/.env" ]; then
  echo "warning: no .env — copy .env.example and add GEMINI_API_KEY for real VLM calls"
fi

if [ "$WITH_SCHP" = 1 ]; then
  bash "$ROOT/scripts/fetch_assets.sh"
else
  bash "$ROOT/scripts/fetch_assets.sh" --yunet-only
  echo "note: parser model not fetched. Use --with-schp for the real SCHP path."
fi

if [ "$WITH_NPM" = 1 ] || [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm ci)
fi

cat <<'EOF'

Next:
  .venv/bin/python -m pytest -q
  .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
  cd frontend && npm run dev
Worktrees: use a different backend port (e.g. 8002) and
  VITE_API_TARGET=http://localhost:8002 npm run dev
EOF
