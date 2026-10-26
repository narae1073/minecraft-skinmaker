# Deployment — home server + Cloudflare Tunnel

Public URL: **https://skin.achijaser.date** (no login; see “Public exposure”).

```
browser ──TLS──> Cloudflare edge ──tunnel──> cloudflared (home) ──http──> 127.0.0.1:8001
                                                                        uvicorn
                                                             FastAPI + frontend/dist + /static
```

The existing `me.achijaser.date` tunnel (`quartz-me`) is **not modified**; this
app uses a separate tunnel named `skinmaker`.

## Host assumptions

- Repo at `/home/achi/Programming/skinmaker`, user `achi`, venv at `.venv`.
- `cloudflared` installed at `/usr/bin/cloudflared` (2026.10.1+).
- `achijaser.date` is on Cloudflare.
- The machine stays on and has ~46 GB free disk.

## One-time setup

### 1. Assets, build, and `.env`

```bash
cd /home/achi/Programming/skinmaker
.venv/bin/pip install -r requirements.txt
scripts/fetch_assets.sh              # YuNet + SCHP
cp .env.example .env                 # then set GEMINI_API_KEY
chmod 600 .env
(cd frontend && npm ci && npm run build)
```

`.env` holds `GEMINI_API_KEY`, `SKINMAKER_TRANSPORT=gemini`,
`SKINMAKER_PARSING=1`, and the public guards
(`SKINMAKER_RATE_LIMIT_PER_MIN`, `SKINMAKER_MAX_UPLOAD_MB`,
`SKINMAKER_RETENTION_DAYS`). It is gitignored and must stay `600`.

### 2. Create the tunnel and DNS

```bash
cloudflared tunnel create skinmaker
# prints the UUID and writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns skinmaker skin.achijaser.date
```

Create `~/.cloudflared/skinmaker.yml` from `deploy/skinmaker.yml.example`,
replacing `<TUNNEL_UUID>`, then validate:

```bash
cloudflared tunnel ingress validate --config ~/.cloudflared/skinmaker.yml
```

The ingress must point at `http://127.0.0.1:8001`.

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

After a PR is merged to `master`:

```bash
./scripts/deploy.sh            # pull, pip, build, test, restart, health check
./scripts/deploy.sh --skip-tests   # emergency only
./scripts/deploy.sh --no-pull      # deploy the current checkout (hotfix)
```

Agents never deploy from a feature branch; the script refuses non-`master`.
Frontend changes require the build step, which the script always runs.

## Retention

`backend/static/skins` and `backend/static/steps` grow with every request.
`skinmaker-cleanup.timer` runs weekly and deletes files older than
`SKINMAKER_RETENTION_DAYS` (default 14). Manual run:

```bash
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
git log --oneline -5
git reset --hard <previous-sha>
./scripts/deploy.sh --no-pull --skip-tests
```

The tunnel can stay up (it proxies whatever the app serves). To take the site
offline without touching `me.achijaser.date`:
`sudo systemctl stop cloudflared-skinmaker`.
