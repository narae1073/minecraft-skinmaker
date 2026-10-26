# Codex devbox (Docker + SSH over Tailscale)

A dedicated Linux workspace for the second developer's **Codex** agent. It is a
separate clone of the repo mounted into a container, reachable only on the
Tailscale network, with Codex preinstalled. The host's public app, production
`.env`, systemd units, Docker socket and cloudflared credentials are **not**
inside the container.

```
Windows (Tailscale)
  │ ssh -p 2222 dev@100.110.156.108
  ▼
Docker container "skinmaker-codex"
  ├─ /workspace   separate clone (skinmaker-codex)
  ├─ /home/dev    persistent volume (Codex auth, gh auth, SSH config)
  ├─ Python 3.12 + Node 24 + git + gh + Codex CLI
  └─ sshd :22  → host tailnet IP :2222
```

The host owner still runs production: `./scripts/deploy.sh` on the host.
The trusted collaborator may also `ssh achi@<tailnet>` for production access.

## 1. Host: one-time setup

Prerequisites: Docker, Tailscale up, Node/Python on the host (for the initial
venv/node_modules bootstrap).

```bash
cd /home/achi/Programming/skinmaker

# Create the partner's SSH key on their Windows machine first, then:
./scripts/devbox_setup.sh --key /path/to/codex.pub
```

This script:

- clones `https://github.com/narae1073/minecraft-skinmaker.git` to
  `/home/achi/Programming/skinmaker-codex` (a **separate clone**);
- creates a local `.env` with `SKINMAKER_TRANSPORT=mock` (never the production key);
- bootstraps `.venv`, dependencies, YuNet + SCHP, and `frontend/node_modules`;
- writes `deploy/dev/.env` with the current Tailscale IPv4;
- builds and starts `skinmaker-codex` on `<tailnet-ip>:2222`.

Re-run it after `tailscale ip -4` changes. Add another key later with
`./scripts/devbox_setup.sh --key other.pub` (it appends, then recreates the
container).

## 2. Partner: Windows setup

1. Install **Tailscale** and accept the owner's tailnet invite.
2. Install **OpenSSH client** if needed (`ssh` is built into Windows 10/11).
3. Put the private key at `%USERPROFILE%\.ssh\skin_codex`.

`%USERPROFILE%\.ssh\config`:

```
Host skin-codex
  HostName 100.110.156.108
  Port 2222
  User dev
  IdentityFile ~/.ssh/skin_codex
  IdentitiesOnly yes
  ServerAliveInterval 30
```

MagicDNS name (`achijaser.tail63f807.ts.net`) works too, but the IP is the most
predictable.

```powershell
ssh skin-codex
```

First login inside the container:

```bash
codex login --device-auth        # open the printed URL on Windows
# or: printenv OPENAI_API_KEY | codex login --with-api-key
gh auth login                    # their own GitHub account
cd /workspace
.venv/bin/python -m pytest -q    # 513 tests
```

Codex can be run directly in `/workspace`:

```bash
codex
```

Because the container is the sandbox, do not try to nest Codex's own sandbox if
it complains; use `codex --dangerously-bypass-approvals-and-sandbox` or set
`sandbox_mode = "danger-full-access"` in `~/.codex/config.toml`. The container
has no host credentials.

## 3. VS Code Remote-SSH (recommended UI)

Remote-SSH → host `skin-codex` → open `/workspace`. VS Code forwards 8001/5173
automatically. For a plain SSH session:

```bash
ssh -L 8001:localhost:8001 -L 5173:localhost:5173 skin-codex
```

Inside the container:

```bash
set -a; source .env; set +a
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
cd frontend && npm run dev
```

The host's production app also uses 8001, but the container has its own network
namespace, so there is no conflict. Only port 2222 is published.

## 4. Workflow

- The Codex clone is on `master`; create `feat/<topic>` branches and open PRs.
- CI runs Ubuntu + Windows + web; `master` requires approval.
- Merge from GitHub; the host owner deploys with `./scripts/deploy.sh`.
- Production access (trusted): from Windows, `ssh achi@<tailnet-ip>` and run the
  deploy script. Do not mount the production checkout into the container.
- Never commit `out/`, `backend/static/`, `frontend/dist/`, `.env`, models, or
  `~/.codex`/gh credentials.

## 5. Security / operations

- SSH is key-only, user `dev`, no root login, no password.
- Port 2222 binds to the **Tailscale IPv4 only**; it is not public. Docker
  published ports bypass UFW, so never change it to `0.0.0.0`.
- Limits: 2 CPUs, 4 GB RAM, 1024 pids. The container has no Docker socket, no
  host network, no systemd, no cloudflared credentials, no production `.env`.
- The host owner's Tailscale SSH remains enabled; the collaborator is trusted
  and may access production.
- Codex/GitHub credentials live in the `skinmaker-codex-home` volume, not the repo.
- The image pins `@openai/codex@0.164.0`; bump it deliberately and rebuild.
- Rebuilding the image changes the container's SSH host key; remove the old
  entry with `ssh-keygen -R "[100.110.156.108]:2222"` or accept the prompt.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| `docker compose up` port bind fails | Tailscale IP changed → rerun `scripts/devbox_setup.sh` |
| SSH permission denied | public key in `/home/achi/.ssh/skinmaker-codex_authorized_keys`; file mode 600; rerun setup |
| `Connection refused` | `docker compose -f deploy/dev/compose.yaml ps`; `docker logs skinmaker-codex` |
| Host key changed | image rebuilt; `ssh-keygen -R "[<ip>]:2222"` |
| Codex cannot write | worktree ownership; container runs UID 1000, clone owned by `achi` |
| Codex sandbox error | use `--dangerously-bypass-approvals-and-sandbox` (container is the sandbox) |
| Tests slow | SCHP is installed; tests with it take ~3 min, without ~10 s |
