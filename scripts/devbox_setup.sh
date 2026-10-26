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
# No Gemini key yet -> mock, so the dev app works without paid API calls.
transport="$(grep '^SKINMAKER_TRANSPORT=' "$WORKSPACE/.env" 2>/dev/null | tail -n1 | cut -d= -f2-)"
if ! grep -Eq '^GEMINI_API_KEY=.+' "$WORKSPACE/.env" \
   && { [ -z "$transport" ] || [ "$transport" = "gemini" ]; }; then
  if grep -q '^SKINMAKER_TRANSPORT=' "$WORKSPACE/.env"; then
    sed -i 's/^SKINMAKER_TRANSPORT=.*/SKINMAKER_TRANSPORT=mock/' "$WORKSPACE/.env"
  else
    printf '\nSKINMAKER_TRANSPORT=mock\n' >> "$WORKSPACE/.env"
  fi
fi

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

# Preserve the optional Codex helper fallback across runs.
install_codex="$(grep '^INSTALL_CODEX=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
[ -n "$install_codex" ] || install_codex=0

cat > "$ENV_FILE" <<EOF
TAILSCALE_IP=$TAILSCALE_IP
WORKSPACE_PATH=$WORKSPACE
AUTHORIZED_KEYS_FILE=$AUTH
INSTALL_CODEX=$install_codex
EOF
chmod 600 "$ENV_FILE"

echo "== docker compose up"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --build
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" ps

# Named home volumes don't pick up image .bashrc changes; migrate the old
# /workspace cd path in an existing volume to /home/dev/workspace.
sleep 1
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" exec -T -u dev codex sh -c '
  if [ -f /home/dev/.bashrc ] && ! grep -q "/home/dev/workspace" /home/dev/.bashrc; then
    sed -i "s#/workspace#/home/dev/workspace#g" /home/dev/.bashrc
  fi
' >/dev/null 2>&1 || true

if [ "$BOOTSTRAP" = 1 ]; then
  echo "== bootstrapping inside the container (venv, models, node_modules)"
  sleep 2
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE" exec -T -u dev codex \
    bash -lc 'cd /home/dev/workspace && ./scripts/dev_setup.sh --with-schp'
fi

cat <<EOF

Remote devbox is up.
  SSH: dev@${TAILSCALE_IP}  port 2222
  (MagicDNS: dev@achijaser.tail63f807.ts.net)

In the Windows Codex GUI, add a remote project:
  host ${TAILSCALE_IP}, port 2222, user dev, key ~/.ssh/skin_codex
  project path /home/dev/workspace

Inside (GUI terminal or ssh):
  gh auth login
  cd /home/dev/workspace && .venv/bin/python -m pytest -q

Production access (trusted, you allowed it): ssh achi@${TAILSCALE_IP}
EOF

if [ "$install_codex" = "1" ]; then
  cat <<EOF

Codex CLI: installed (INSTALL_CODEX=1). If the GUI asks for auth:
  codex login --device-auth
EOF
else
  cat <<EOF

Codex CLI: not installed (default). If the GUI requires a remote helper:
  set INSTALL_CODEX=1 in deploy/dev/.env and rerun this script.
EOF
fi
