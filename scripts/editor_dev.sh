#!/usr/bin/env bash
# Start the developer mask editor (tools/mask_editor) on localhost.
#
#   ./scripts/editor_dev.sh              # port 8765, token from out/mask_editor/access_token
#   PORT=8766 ./scripts/editor_dev.sh    # another port
#   PUBLISH=0 ./scripts/editor_dev.sh    # hide "프로덕션에 반영"
#
# The editor writes drafts to out/mask_editor/ and never touches the production
# asset unless the publish button is used (and even then only the checkout).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8765}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/.venv/Scripts/python.exe"
if [ ! -x "$PY" ]; then
  echo "venv missing: run ./scripts/dev_setup.sh first" >&2
  exit 1
fi

TOKEN_FILE="$ROOT/out/mask_editor/access_token"
if [ -n "${SKINMAKER_EDITOR_TOKEN:-}" ]; then
  TOKEN="$SKINMAKER_EDITOR_TOKEN"
elif [ -f "$TOKEN_FILE" ]; then
  TOKEN="$(tr -d '\n' < "$TOKEN_FILE")"
else
  mkdir -p "$ROOT/out/mask_editor"
  TOKEN="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE" 2>/dev/null || true
  echo "created $TOKEN_FILE"
fi

if [ "${PUBLISH:-1}" = "1" ]; then
  export SKINMAKER_EDITOR_ALLOW_PUBLISH=1
fi
export SKINMAKER_EDITOR_TOKEN="$TOKEN"

if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "port $PORT is already in use (is the editor running?)" >&2
  exit 1
fi

echo "editor: http://127.0.0.1:${PORT}/"
echo "token:  $TOKEN"
echo "publish: ${SKINMAKER_EDITOR_ALLOW_PUBLISH:-0}"
exec "$PY" -m uvicorn --app-dir tools/mask_editor app:app --host 127.0.0.1 --port "$PORT"
