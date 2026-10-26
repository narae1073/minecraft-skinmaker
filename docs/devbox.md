# Remote devbox for the Codex GUI (Docker + SSH over Tailscale)

A dedicated Linux workspace for the second developer. **Codex runs in the
Windows GUI**; the GUI adds this container as a **remote project over SSH**. The
image is the workspace: Python 3.12, Node 24, git, gh, sshd. The Codex CLI is
**not installed by default**, but this host runs with `INSTALL_CODEX=1` because
the GUI's remote-project mode requires the remote CLI.

```
Windows Codex GUI (local auth)
   │ Tailscale + SSH :2222
   ▼
Docker container "skinmaker-codex"
  ├─ /workspace   separate clone (skinmaker-codex)
  ├─ /home/dev    persistent volume (SSH/GitHub config)
  ├─ Python 3.12 + Node 24 + git + gh + rsync + sshd
  └─ no production .env / Docker socket / systemd / cloudflared
```

The host's public app, production `.env`, systemd units, Docker socket and
cloudflared credentials are **not** inside the container. The trusted
collaborator may still `ssh achi@<tailnet>` for production access, but the
devbox itself has no host credentials.

## 1. Host: one-time setup

Prerequisites: Docker and Tailscale up on the host. Python/Node are inside the
image; the host does not need them for this workspace.

```bash
cd /home/achi/Programming/skinmaker

# Create the partner's SSH key on their Windows machine first, then:
./scripts/devbox_setup.sh --key /path/to/codex.pub
```

This script:

- clones `https://github.com/narae1073/minecraft-skinmaker.git` to
  `/home/achi/Programming/skinmaker-codex` (a **separate clone**);
- creates a local `.env` with `SKINMAKER_TRANSPORT=mock` when no Gemini key is
  present (never the production key);
- bootstraps `.venv`, dependencies, YuNet + SCHP, and `frontend/node_modules`
  **inside the container** (the venv is container-specific; do not run
  `dev_setup.sh` on the host for this clone);
- writes `deploy/dev/.env` with the current Tailscale IPv4;
- builds and starts `skinmaker-codex` on `<tailnet-ip>:2222`.

`--no-bootstrap` starts/recreates without the dependency install. Adding a key
later appends it and recreates the container:

```bash
./scripts/devbox_setup.sh --key /path/to/another.pub --no-bootstrap
```

### Verified 2026-10-26

- SSH from the host with a test key works (`dev`, key-only).
- `INSTALL_CODEX=1` on this host: **Codex CLI 0.164.0** at `/usr/bin/codex`
  (the GUI's remote-project mode requires it); login not configured yet.
  Node 24.22, Python 3.12.15, `gh` 2.103, `rsync` available.
- `pytest -q` inside `/workspace`: **513 passed** (5.5 min with SCHP).
- `npm run build` succeeds; `uvicorn` + health/root return `ok` / 200 with
  `SKINMAKER_TRANSPORT=mock`.
- Port is bound only to `100.110.156.108:2222`; limits 4 GB / 2 CPU / 1024 pids;
  `no-new-privileges` enabled.
- The partner's Codex GUI remote-project connection is the remaining acceptance
  gate (account-level; not testable from the host).

## 2. Partner: Windows setup

1. Install **Tailscale** and accept the owner's tailnet invite.
2. Install **OpenSSH client** if needed (`ssh` is built into Windows 10/11).
3. Put the private key at `%USERPROFILE%\.ssh\skin_codex`.

`%USERPROFILE%\.ssh\config` (also lets the GUI use a host alias):

```
Host skin-codex
  HostName 100.110.156.108
  Port 2222
  User dev
  IdentityFile ~/.ssh/skin_codex
  IdentitiesOnly yes
  ServerAliveInterval 30
```

MagicDNS (`achijaser.tail63f807.ts.net`) works too, but the IP is predictable.

### Add the remote project in the Codex GUI

Use these values:

- **SSH host**: `100.110.156.108` (or `achijaser.tail63f807.ts.net`)
- **Port**: `2222`
- **User**: `dev`
- **Key**: `~/.ssh/skin_codex`
- **Project path**: `/workspace`

Codex authentication/model choice normally stays in the **GUI on Windows**. The
GUI's remote-project mode requires the remote CLI; this host enables it with
`INSTALL_CODEX=1`. If the GUI (or the CLI) asks for a login:

```bash
codex login --device-auth
```

Open the printed URL on Windows; the auth lands in `/home/dev/.codex` (the
persistent home volume).

### First terminal inside the project

```bash
gh auth login                    # their own GitHub account
cd /workspace
.venv/bin/python -m pytest -q    # 513 tests
```

## 3. VS Code Remote-SSH (optional)

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

The host's production app uses 8001, but the container has its own network
namespace. Only port 2222 is published.

## 4. Workflow

- The clone is on `master`; create `feat/<topic>` branches and open PRs.
- CI runs Ubuntu + Windows + web; `master` requires approval.
- Merge from GitHub; the host owner deploys with `./scripts/deploy.sh`.
- Production access (trusted): from Windows, `ssh achi@<tailnet-ip>` and run the
  deploy script. Do not mount the production checkout into the container.
- Never commit `out/`, `backend/static/`, `frontend/dist/`, `.env`, or models.

## 5. Fallback: GUI needs a remote helper (enabled on this host)

The default image has **no Codex CLI**. The GUI's remote-project feature can
require one; when that happens, opt in explicitly:

```bash
# deploy/dev/.env
INSTALL_CODEX=1
```

Then rebuild:

```bash
./scripts/devbox_setup.sh --no-bootstrap
```

**This host is currently running with `INSTALL_CODEX=1`** (the GUI reported
"Codex CLI is not installed on this remote machine"). `scripts/devbox_setup.sh`
preserves the value across runs. The image pins `@openai/codex@0.164.0`;
authenticate with `codex login --device-auth` inside the container if the GUI
asks. To remove it later, set `INSTALL_CODEX=0` and rebuild.

## 6. Security / operations

- SSH is key-only, user `dev`, no root login, no password.
- Port 2222 binds to the **Tailscale IPv4 only**; it is not public. Docker
  published ports bypass UFW, so never change it to `0.0.0.0`.
- Limits: 2 CPUs, 4 GB RAM, 1024 pids. No Docker socket, host network, systemd,
  cloudflared credentials, or production `.env`.
- The host owner's Tailscale SSH remains enabled; the collaborator is trusted and
  may access production.
- GitHub credentials live in the `skinmaker-codex-home` volume, not the repo.
- Rebuilding the image changes the container's SSH host key; remove the old
  entry with `ssh-keygen -R "[100.110.156.108]:2222"` or accept the prompt.

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| `docker compose up` port bind fails | Tailscale IP changed → rerun `scripts/devbox_setup.sh` |
| SSH permission denied | public key in `/home/achi/.ssh/skinmaker-codex_authorized_keys`; file mode 600; rerun setup |
| `Connection refused` | `docker compose -f deploy/dev/compose.yaml ps`; `docker logs skinmaker-codex` |
| Host key changed | image rebuilt; `ssh-keygen -R "[<ip>]:2222"` |
| GUI cannot add remote project | verify `ssh skin-codex` works first; then use the same host/port/user/key in the GUI |
| GUI asks for a remote Codex helper | this host already has `INSTALL_CODEX=1`; if not, §5 |
| Tests slow | SCHP is installed; tests with it take ~5 min in the 2-CPU container, without ~10 s |
