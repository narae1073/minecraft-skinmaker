#!/usr/bin/env bash
# Deploy the current master on the home host.
#
#   ./scripts/deploy.sh                 # pull, install, build, test, restart
#   ./scripts/deploy.sh --skip-tests    # emergency hotfix
#   ./scripts/deploy.sh --no-pull       # deploy the current checkout
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKIP_TESTS=0
NO_PULL=0
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=1 ;;
    --no-pull) NO_PULL=1 ;;
    *) echo "usage: $0 [--skip-tests] [--no-pull]" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" != "master" ]; then
  echo "refusing to deploy branch '$branch' (expected master)" >&2
  exit 1
fi
if [ ! -f "$ROOT/.env" ]; then
  echo "missing .env — copy .env.example and add GEMINI_API_KEY" >&2
  exit 1
fi
chmod 600 "$ROOT/.env"

if [ "$NO_PULL" = 0 ]; then
  git pull --ff-only
fi

echo "== python deps"
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt"

echo "== assets"
if [ ! -s "$ROOT/assets/face_detection_yunet_2023mar.onnx" ]; then
  bash "$ROOT/scripts/fetch_assets.sh" --yunet-only
fi
if [ ! -s "$ROOT/out/models/schp-atr-18-int8-static.onnx" ]; then
  echo "warning: SCHP model missing; parsing will fall back to bands" >&2
fi

echo "== frontend"
(
  cd "$ROOT/frontend"
  npm ci
  npm run lint
  npm run build
)

if [ "$SKIP_TESTS" = 0 ]; then
  echo "== tests"
  "$ROOT/.venv/bin/python" -m pytest -q
fi

echo "== restart"
sudo systemctl restart skinmaker

for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8001/api/v1/health >/dev/null 2>&1; then
    curl -fsS http://127.0.0.1:8001/api/v1/health
    echo
    echo "deployed: https://skin.achijaser.date"
    exit 0
  fi
  sleep 1
done

echo "health check failed; see: journalctl -u skinmaker -n 80 --no-pager" >&2
exit 1
