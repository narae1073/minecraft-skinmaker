# No Photo Retention — design (2026-11-05)

## Intent

A visitor uploads a photo to create a Minecraft skin. The original photo must
not remain on the server after the request, and the operator must not be able
to browse other people's photos. The generated 64×64 skin and a photo-free
processing sheet may stay public.

## Current problem

- `origin/master` writes the raw upload to `backend/static/skins/input_*` and
  returns it as `data.input`. `/static` is public and has no auth. The release
  clone currently holds 2,559 such files.
- The processing sheets under `backend/static/steps/` embed the source photo:
  the S0 panel is the photo, the S1 panel is a photo crop, and the mask panel
  overlays the photo. The release clone holds 4,688 files.
- `feat/skin-owner-edit` moves inputs to `backend/private/inputs/` and serves
  them only to the owner cookie. The operator can still read the files, so this
  does not meet the goal.

## Goals

- No raw upload is written to a persistent location.
- The generation response has no `input` URL.
- Public processing sheets contain no source-photo pixels. They keep a
  text-only quality panel, a class-colored parsing silhouette, color swatches,
  and the skin-only atlas/UV/preview panels.
- Legacy `input_*` files and photo-bearing steps files are purged; old URLs
  return 404.
- `feat/skin-owner-edit` must not reintroduce input storage before it merges.

## Non-goals

- Preventing root from instrumenting the live process, Cloudflare from seeing
  the TLS payload, or copies in host backups/snapshots.
- Removing generated skins or the per-skin editor.
- Client-side processing or encryption at rest.

## Decisions

- **Option A — no retention** (chosen over owner-only + TTL and status quo).
  The request still buffers the upload in memory; the app writes no persistent
  copy. `quality.inspect` accepts bytes so the app no longer creates its own
  temp file.
- The public processing sheet keeps the parsing step as a class-colored
  silhouette (no photo) and the color step as swatches (no photo crops).
- The original-photo comparison card on the owner-edit branch uses a browser
  object URL only. `origin/master` already has no such card.
- Ship a hotfix off `origin/master` first. Rebase `feat/skin-owner-edit` and
  remove its private-input storage before that branch's PR.

## Acceptance

- `POST /api/v1/generate-skin` returns no `input`; no `input_*` file is
  created; the app leaves no temp file.
- `steps=1` produces sheets with no source-photo pixels and still shows the
  quality, parsing, color, and skin panels.
- `scripts/purge_photo_artifacts.sh --yes` removes `input_*`, steps files, and
  legacy private inputs while keeping result skins.
- Full pytest, `npm run lint`, and `npm run build` pass.

## Residual risks

- A root operator can still instrument the running process.
- Cloudflare terminates TLS and may see the upload body.
- Starlette may spool large uploads to disk for the duration of the request.
- Host backups/snapshots and Cloudflare caches may keep old URLs until purged.
- The owner-edit job records store derived fabric crops, not the original
  photo; they remain operator-readable.
