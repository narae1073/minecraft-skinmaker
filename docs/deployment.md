# Deployment — home server + Cloudflare Tunnel

Public URL: **https://skin.achijaser.date** (no login; see “Public exposure”).

```
browser ──TLS──> Cloudflare edge ──tunnel──> cloudflared (home) ──http──> 127.0.0.1:8001
                                                                        uvicorn
                                                             FastAPI + frontend/dist + /static
```

The existing `me.achijaser.date` tunnel (`quartz-me`) is **not modified**; this
app uses a separate tunnel named `skinmaker`.

## Automatic merge + deploy (2026-10-27)

```
DSH dev checkout   /home/achi/Programming/skinmaker
Codex devbox       /home/achi/Programming/skinmaker-codex  (container /home/dev/workspace)
        │
        ├─ PR → CI → 1 approval → gh pr merge --auto --rebase
        ▼
   master push
        │
        ▼
self-hosted runner "skinmaker-home" (label skinmaker-deploy)
  → /home/achi/Programming/skinmaker-release/scripts/deploy.sh
       pull → pip → npm ci/build → pytest → systemctl restart skinmaker
        ▼
https://skin.achijaser.date
```

- Production uses a **dedicated release clone**:
  `/home/achi/Programming/skinmaker-release`; systemd `WorkingDirectory` and
  `ExecStart` point there, and `deploy.sh` lives there.
- Dev checkouts are separate: DSH on `/home/achi/Programming/skinmaker` (mock
  `.env`), Codex on the devbox clone. They never need to be clean for a deploy.
- The self-hosted runner runs `.github/workflows/deploy.yml` on `push: master`.
  It is registered with labels `self-hosted, linux, skinmaker-deploy`.
- Agents enable auto-merge after opening a PR:
  `gh pr merge --auto --rebase`; the other person/agent approves; GitHub merges
  when CI is green; the deploy workflow runs.
- Manual fallback on the host only:
  `cd /home/achi/Programming/skinmaker-release && ./scripts/deploy.sh`.

**Verified 2026-10-27:** production switched to the release clone; public
`/` and health 200; runner `skinmaker-home` online. The release clone has its
own venv, `.env`, `backend/static`, `out/models`, `assets`, and
`frontend/dist`.

**Verified 2026-10-26:** tunnel `skinmaker` (UUID
`866fd5b7-5046-4fd7-80a1-2f7b0ae30502`) connected; `skinmaker`,
`cloudflared-skinmaker`, and `skinmaker-cleanup.timer` active and enabled;
`https://skin.achijaser.date/` 200, health 200, one real upload 200 with skin /
input / steps URLs, public static assets 200, no-face 422, 16 MB 413, 429 after
the limit. `scripts/deploy.sh --no-pull --skip-tests` verified. The Cloudflare
WAF rate-limit rule in §4 is still a manual dashboard step.

## Host assumptions

- **Release** clone at `/home/achi/Programming/skinmaker-release`, user `achi`,
  venv at `.venv`.
- Dev clones: `/home/achi/Programming/skinmaker` (DSH) and
  `/home/achi/Programming/skinmaker-codex` (Codex devbox). These are never the
  deploy target.
- Self-hosted GitHub Actions runner at `/home/achi/actions-runner`, service
  `actions.runner.narae1073-minecraft-skinmaker.skinmaker-home`.
- `cloudflared` installed at `/usr/bin/cloudflared` (2026.10.1+).
- `achijaser.date` is on Cloudflare.
- The machine stays on and has ~40 GB free disk.

## One-time setup

### 1. Release clone, assets, build, and `.env`

```bash
git clone https://github.com/narae1073/minecraft-skinmaker.git \
  /home/achi/Programming/skinmaker-release
cd /home/achi/Programming/skinmaker-release
python3.12 -m venv .venv          # or: virtualenv -p /usr/bin/python3.12 .venv
.venv/bin/pip install -r requirements-dev.txt
scripts/fetch_assets.sh              # YuNet + SCHP
cp .env.example .env                 # then set GEMINI_API_KEY
chmod 600 .env
(cd frontend && npm ci && npm run build)
```

The release clone needs its own `backend/static` (production uploads),
`out/models`, `assets`, and `.env`. The dev checkouts keep their own mock
`.env` and generated files.

`.env` holds `GEMINI_API_KEY`, `SKINMAKER_TRANSPORT=gemini`,
`SKINMAKER_PARSING=1`, and the public guards
(`SKINMAKER_RATE_LIMIT_PER_MIN`, `SKINMAKER_MAX_UPLOAD_MB`,
`SKINMAKER_RETENTION_DAYS`). It is gitignored and must stay `600`.

### 2. Create the tunnel and DNS

```bash
cloudflared tunnel create skinmaker
# prints the UUID and writes ~/.cloudflared/<UUID>.json
```

Create `~/.cloudflared/skinmaker.yml` from `deploy/skinmaker.yml.example`,
replacing `<TUNNEL_UUID>`. **Pass `--config` before the subcommand**: the default
`~/.cloudflared/config.yml` belongs to the existing `quartz-me` tunnel, and
`route dns` / `info` will silently use that tunnel otherwise.

```bash
CFG=~/.cloudflared/skinmaker.yml
cloudflared tunnel --config "$CFG" ingress validate
cloudflared tunnel --config "$CFG" route dns --overwrite-dns skinmaker skin.achijaser.date
```

`--overwrite-dns` is needed if the hostname already has a CNAME (for example
after an accidental route). The ingress must point at `http://127.0.0.1:8001`.

### 3. Install systemd units

```bash
sudo cp deploy/skinmaker.service deploy/cloudflared-skinmaker.service \
        deploy/skinmaker-cleanup.service deploy/skinmaker-cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now skinmaker cloudflared-skinmaker skinmaker-cleanup.timer
```

`skinmaker.service` runs uvicorn on loopback only:
`--host 127.0.0.1 --port 8001 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1`.
Do not bind `0.0.0.0` unless you deliberately want LAN access; the tunnel is the
public path.

### 4. WAF rate limit (outer layer)

Cloudflare dashboard → Security → WAF → Rate limiting rules → create:

- expression: `http.request.method eq "POST" and http.request.uri.path eq "/api/v1/generate-skin"`
- rate: 10 requests / 1 minute, per IP; action Block for 60 seconds.

The app also has an in-process limiter (`SKINMAKER_RATE_LIMIT_PER_MIN`, default
6/min/IP). Cloudflare’s rule is the outer guard and survives app restarts.

### 5. Verify

```bash
curl -s http://127.0.0.1:8001/api/v1/health
systemctl status skinmaker cloudflared-skinmaker --no-pager
curl -I https://skin.achijaser.date/
journalctl -u skinmaker -u cloudflared-skinmaker -n 50 --no-pager
```

Then in a browser: upload a photo, check the three candidates, the 3D viewer,
the processing-steps sheet, and a download. Test the guards:

```bash
# 429 after the per-minute limit
for i in $(seq 1 8); do curl -s -o /dev/null -w '%{http_code}\n' \
  -F "file=@tests/fixtures/messi5.jpg;type=image/jpeg" \
  http://127.0.0.1:8001/api/v1/generate-skin; done

# 413 above SKINMAKER_MAX_UPLOAD_MB (1 MB in this test only)
SKINMAKER_MAX_UPLOAD_MB=1 curl -s -F "file=@tests/fixtures/messi5.jpg;type=image/jpeg" ...
```

## Deploy loop

After a PR is merged to `master`, it is automatic:

1. `push: master` triggers `.github/workflows/deploy.yml`.
2. The self-hosted runner runs `/home/achi/Programming/skinmaker-release/scripts/deploy.sh`.
3. That script pulls `master`, installs, builds, tests, restarts `skinmaker`,
   and health-checks.

Manual fallback on the host only:

```bash
cd /home/achi/Programming/skinmaker-release
./scripts/deploy.sh                 # pull, pip, build, test, restart
./scripts/deploy.sh --skip-tests    # emergency only
./scripts/deploy.sh --no-pull       # current release checkout (hotfix)
```

Agents never deploy from a dev checkout. The deploy script refuses a non-`master`
branch; the release clone must stay clean.

## Retention

`backend/static/skins` and `backend/static/steps` in the **release clone** grow
with every request. `skinmaker-cleanup.timer` runs weekly and deletes files older
than `SKINMAKER_RETENTION_DAYS` (default 14). Manual run:

```bash
cd /home/achi/Programming/skinmaker-release
scripts/cleanup_static.sh
du -sh backend/static
```

Uploaded photos are served under `/static/skins/input_*` and steps sheets at
`/static/steps/*`; both are covered by retention.

## Public exposure

There is **no login**. The decision is intentional; mitigations:

- 15 MB upload cap (rejected before decoding);
- 6/min/IP app limiter + Cloudflare WAF rule;
- 14-day retention and a footer/README notice;
- Gemini key stays server-side in `.env`;
- uvicorn binds loopback, so the tunnel is the only ingress.

If abuse appears: stop the tunnel (`sudo systemctl stop cloudflared-skinmaker`),
rotate `GEMINI_API_KEY`, then re-enable. Adding Cloudflare Access later does not
require code changes.

## Troubleshooting

| Symptom | Check |
|---|---|
| Cloudflare 502/1033 | `systemctl status skinmaker`; app not listening or crashed |
| 404 at `/` | `frontend/dist` missing → `npm run build`, restart |
| Health says `unavailable` | `GEMINI_API_KEY` missing/invalid in `.env` |
| First request very slow | SCHP model missing (falls back) or cold Gemini call |
| Tunnel not connecting | `cloudflared tunnel info skinmaker`, config path, credentials file perms |
| Disk growth | `du -sh backend/static`, run cleanup |
| 429 too aggressive | raise `SKINMAKER_RATE_LIMIT_PER_MIN` in `.env`, restart |

## Rollback

```bash
cd /home/achi/Programming/skinmaker-release
git log --oneline -5
git reset --hard <previous-sha>
./scripts/deploy.sh --no-pull --skip-tests
```

The tunnel can stay up (it proxies whatever the app serves). To take the site
offline without touching `me.achijaser.date`:
`sudo systemctl stop cloudflared-skinmaker`.
