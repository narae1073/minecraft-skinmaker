#!/usr/bin/env bash
# One-time host setup for the Codex devbox.
#
#   ./scripts/devbox_setup.sh --key /path/to/codex.pub
#   ./scripts/devbox_setup.sh --key /path/to/codex.pub --no-bootstrap
#
# Creates a separate clone, bootstraps its venv/models/node_modules, writes
# deploy/dev/.env, and starts the container on the tailnet IP.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/dev/compose.yaml"
ENV_FILE="$ROOT/deploy/dev/.env"
WORKSPACE="${SKINMAKER_CODEX_WORKSPACE:-/home/achi/Programming/skinmaker-codex}"
AUTH="${SKINMAKER_CODEX_AUTHORIZED_KEYS:-/home/achi/.ssh/skinmaker-codex_authorized_keys}"
KEY_FILE=""
BOOTSTRAP=1

while [ $# -gt 0 ]; do
  case "$1" in
    --key) KEY_FILE="${2:-}"; shift 2 ;;
    --workspace) WORKSPACE="${2:-}"; shift 2 ;;
    --no-bootstrap) BOOTSTRAP=0; shift ;;
    *) echo "usage: $0 [--key PUBLIC_KEY] [--workspace PATH] [--no-bootstrap]" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null || { echo "docker missing" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "cannot talk to docker (group/permissions?)" >&2; exit 1; }
command -v tailscale >/dev/null || { echo "tailscale missing" >&2; exit 1; }
TAILSCALE_IP="$(tailscale ip -4 | head -n1)"
[ -n "$TAILSCALE_IP" ] || { echo "tailscale has no IPv4 address (is it up?)" >&2; exit 1; }

if [ ! -d "$WORKSPACE/.git" ]; then
  echo "== cloning workspace: $WORKSPACE"
  mkdir -p "$(dirname "$WORKSPACE")"
  git clone https://github.com/narae1073/minecraft-skinmaker.git "$WORKSPACE"
fi

if [ ! -f "$WORKSPACE/.env" ]; then
  cp "$WORKSPACE/.env.example" "$WORKSPACE/.env"
fi
grep -q '^SKINMAKER_TRANSPORT=' "$WORKSPACE/.env" \
  || printf '\nSKINMAKER_TRANSPORT=mock\n' >> "$WORKSPACE/.env"

mkdir -p "$(dirname "$AUTH")"
touch "$AUTH"
chmod 600 "$AUTH"
if [ -n "$KEY_FILE" ]; then
  [ -s "$KEY_FILE" ] || { echo "key file is empty: $KEY_FILE" >&2; exit 1; }
  key="$(cat "$KEY_FILE")"
  grep -qxF "$key" "$AUTH" || printf '%s\n' "$key" >> "$AUTH"
else
  echo "warning: no --key yet; add one with --key before SSH will work" >&2
fi

if [ "$BOOTSTRAP" = 1 ] && [ ! -e "$WORKSPACE/.venv" ]; then
  echo "== bootstrapping workspace (venv, models, node_modules)"
  (cd "$WORKSPACE" && ./scripts/dev_setup.sh --with-schp)
fi

cat > "$ENV_FILE" <<EOF
TAILSCALE_IP=$TAILSCALE_IP
WORKSPACE_PATH=$WORKSPACE
AUTHORIZED_KEYS_FILE=$AUTH
EOF
chmod 600 "$ENV_FILE"

echo "== docker compose up"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --build
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" ps

cat <<EOF

Codex devbox is up.
  ssh -i <key> -p 2222 dev@${TAILSCALE_IP}
  (MagicDNS: dev@achijaser.tail63f807.ts.net)

Partner first login:
  codex login --device-auth       # or: printenv OPENAI_API_KEY | codex login --with-api-key
  gh auth login
  cd /workspace && .venv/bin/python -m pytest -q

Production access (trusted, you allowed it): ssh achi@${TAILSCALE_IP}
EOF
