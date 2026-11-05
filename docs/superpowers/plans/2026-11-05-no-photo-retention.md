# No Photo Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop retaining or publishing users' original photos, purge the copies already on the public site, and keep the processing sheet useful without the photo.

**Architecture:** The upload stays in memory for the request (`inspect()` accepts bytes, no app-owned temp file). `backend/app.py` no longer writes `input_*` or returns an `input` URL. `skinmaker/debugview.py` gains a `privacy` mode whose panels use only the face metrics, the SCHP class map, measured colors, and the rendered skin. A one-time purge script removes legacy `input_*` files and the existing photo-bearing steps sheets; the weekly cleanup keeps `input_*` from coming back.

**Tech Stack:** Python 3.12, FastAPI, Pillow, numpy, pytest, React 19/Vite (only the footer text changes on master), bash.

**Spec:** `docs/superpowers/specs/2026-11-05-no-photo-retention-design.md` — the plan argues from this document.

## Global Constraints

- Public site has no auth: keep the 15 MB upload cap, 6/min/IP limit, and 14-day retention for generated outputs.
- Generated skins (`/static/skins/*_c*.png`) stay public; only source photos are removed.
- No new runtime or dev dependencies.
- Use `.venv/bin/python`; never `python` or `uv`.
- TDD: write the failing test, run it, implement the minimum, run it green, commit.
- Run pytest unpiped and check the exit code. Run full suite before the PR.
- Never commit `out/`, `backend/static/`, `frontend/dist/`, `.env`, `*.onnx`, or generated steps/skins.
- Branch `fix/no-photo-retention` off `origin/master`; no push to `master`; PR + 1 approval.
- Windows CI runs the same suite; skip the bash-script test when `bash` is unavailable or `os.name == "nt"`.

## Review Focus

- **A steps request must not publish the source photo.** The old S0/S1/mask panels render `photo.image`; a privacy mode that silently falls back to them would keep the leak. The unit test monkeypatches those panel functions to raise, and the backend test asserts `privacy=True` is passed.
- **A failed request must not leave an original behind.** `inspect()` now reads the bytes directly, so an exception after upload cannot leave an app temp file. The no-face and bad-image tests still exercise the 400/422 paths.
- **The API must not advertise a URL that is gone.** Removing the file write without removing `data.input` would make the frontend request a 404. The contract test asserts the key is absent.
- **The purge must not delete result skins.** The purge test creates a result skin beside an `input_*` file and asserts only the input is removed.
- **The owner-edit branch must not resurrect input storage.** `feat/skin-owner-edit` has its own `private/inputs` code; Task 6 removes it before that branch merges.

---

### Task 1: Inspect uploads in memory

**Files:**
- Modify: `skinmaker/quality.py:228-280` (the `inspect` function and the unreachable duplicate below it)
- Modify: `backend/app.py:242-259` (the `mkstemp` block)
- Test: `tests/test_quality.py`

**Interfaces:**
- Consumes: `FaceBox`, `PhotoInput`, `plan_degradation`, `detect_person`, `_multiscale_face` (unchanged).
- Produces: `inspect(source: str | Path | bytes | bytearray, score_min: float = DETECT_SCORE_MIN, crop: FaceBox | None = None) -> PhotoInput`. For `bytes`/`bytearray`, `PhotoInput.path` is `"<upload>"`. The backend calls `inspect(raw, crop=crop_box)` with the bytes it already read.

- [ ] **Step 1: Write the failing test**

```python
def test_inspect_accepts_image_bytes():
    raw = (FIXTURES / "lena.jpg").read_bytes()
    from_path = Q.inspect(FIXTURES / "lena.jpg")
    from_bytes = Q.inspect(raw)
    assert from_bytes.image.size == from_path.image.size
    assert from_bytes.face == from_path.face
    assert from_bytes.path == "<upload>"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_quality.py::test_inspect_accepts_image_bytes -v`
Expected: FAIL with `TypeError`/`AttributeError` because `Path(raw)` is not accepted.

- [ ] **Step 3: Implement the bytes branch**

Add `import io` at the top of `skinmaker/quality.py`. At the start of `inspect`:

```python
def inspect(source: str | Path | bytes | bytearray, score_min: float = DETECT_SCORE_MIN,
            crop: FaceBox | None = None) -> PhotoInput:
    if isinstance(source, (bytes, bytearray)):
        im = Image.open(io.BytesIO(source))
        label = "<upload>"
    else:
        p = Path(source)
        im = Image.open(p)
        label = str(p)
    with im:
        image = ImageOps.exif_transpose(im).convert("RGB")
        # ... existing body, replacing str(p) with label in PhotoInput(...)
```

Delete the unreachable duplicate block after the first `return` (the second `p = Path(path)` through the old return). It cannot run and references the removed `path` variable.

- [ ] **Step 4: Update the backend to pass the bytes**

Replace the `mkstemp`/`write`/`inspect(tmp_name)`/`unlink` block in `backend/app.py` with:

```python
await stage("inspect", 8, "인물과 얼굴을 찾는 중이에요")
_t = time.perf_counter()
try:
    photo = await _await_or_cancel(request, inspect, raw, crop=crop_box)
    timings["inspect"] = round(time.perf_counter() - _t, 3)
except Exception as exc:
    fail(400, "unreadable", f"이미지를 읽지 못했어요: {type(exc).__name__}")
```

Remove `import tempfile` from `backend/app.py`. Keep `import os` for `os.environ`.

- [ ] **Step 5: Run the focused tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_quality.py tests/test_backend.py -q`
Expected: PASS (the existing no-face, bad-image, and backend tests still pass).

- [ ] **Step 6: Commit**

```bash
git add skinmaker/quality.py backend/app.py tests/test_quality.py
git commit -m "fix: inspect uploads in memory"
```

---

### Task 2: Stop writing and returning the input photo

**Files:**
- Modify: `backend/app.py` (remove `IMAGE_SUFFIX`, `_image_suffix`, `input_name`, the `write_bytes`, and `"input"` in the response)
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `inspect(raw)` from Task 1.
- Produces: `POST /api/v1/generate-skin` response `data` has no `input` key and writes no `input_*` file. `backend.app.STATIC_DIR` still holds generated `*_c*.png` and `*_c*_flat.png` files.

- [ ] **Step 1: Write the failing test**

```python
def test_generate_does_not_store_or_return_the_input_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "STATIC_DIR", tmp_path)
    with PHOTO.open("rb") as f:
        r = client().post(
            "/api/v1/generate-skin",
            files={"file": ("evil.html", f, "image/jpeg")},
            data={"steps": "0"},
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "input" not in data
    assert not list(tmp_path.glob("input_*")), "raw upload must not be stored"
    assert list(tmp_path.glob("*_c1.png")), "generated skins still go to STATIC_DIR"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_backend.py::test_generate_does_not_store_or_return_the_input_photo -v`
Expected: FAIL because `data["input"]` exists and/or `input_*` is written.

- [ ] **Step 3: Remove the input storage**

In `backend/app.py`:

- Delete `IMAGE_SUFFIX` and `_image_suffix`.
- Delete `input_name = ...` and `(STATIC_DIR / input_name).write_bytes(raw)`.
- Delete `"input": f"/static/skins/{input_name}",` from the response.
- Remove `io` and `from PIL import Image` imports if they are now unused (check with grep before deleting; `Image` is only used by `_image_suffix`).
- Keep `token = uuid.uuid4().hex[:12]`; it names the skins and steps.

Replace the two old tests:

- `test_upload_is_stored_with_extension_from_image_format` → the new test above.
- `test_generate_returns_input_photo_url` → delete it; the new test covers the absence.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backend.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_backend.py
git commit -m "fix: do not persist uploaded photos"
```

---

### Task 3: Photo-free processing sheets

**Files:**
- Modify: `skinmaker/debugview.py` (new panels, privacy sets, `steps_sheets`/`build_panels` flags)
- Modify: `backend/app.py` (call `steps_sheets(..., privacy=True)`)
- Test: `tests/test_debugview.py`, `tests/test_backend.py`

**Interfaces:**
- Consumes: `PhotoInput`, `MASK_COLORS`, `ObservedColors`, `Panel`, `contact_sheet`.
- Produces:
  - `panel_quality(photo: PhotoInput) -> Panel` — text-only; title `"S0 quality"`.
  - `panel_mask_silhouette(seg) -> Panel | None` — colors `seg` classes on a neutral background; title `"S1b parsing mask"`.
  - `panel_swatches(observed) -> Panel` — color chips and metrics only; title `"S1 observed colors"`.
  - `PANEL_STRIP_PRIVACY = ("quality", "mask", "swatches", "atlas")`
  - `PANELS_PRIVACY = ("quality", "mask", "swatches", "atlas", "uvmap", "preview")`
  - `steps_sheets(..., privacy: bool = False)`
  - `build_panels(..., privacy: bool = False)`

- [ ] **Step 1: Write the failing tests**

In `tests/test_debugview.py`:

```python
def test_privacy_steps_skip_photo_panels(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("photo panel used in privacy mode")

    for name in ("panel_s0", "panel_s1", "panel_mask", "panel_reject"):
        monkeypatch.setattr(DV, name, boom)

    import numpy as np
    from skinmaker import colors as C

    photo = photo_input()
    skin = build_placeholder("classic").image
    observed = C.extract(photo)
    seg = np.zeros(photo.image.size[::-1], np.uint8)
    seg[200:400, 200:400] = 4

    clean, full = DV.steps_sheets(photo, skin, "classic", observed=observed, seg=seg, privacy=True)
    assert clean.width > 0 and full.width > 0


def test_privacy_panel_set_has_no_photo_titles():
    import numpy as np
    from skinmaker import colors as C

    photo = photo_input()
    skin = build_placeholder("classic").image
    observed = C.extract(photo)
    seg = np.zeros(photo.image.size[::-1], np.uint8)
    panels = DV.build_panels(
        photo, skin, "classic", observed=observed, seg=seg,
        which=DV.PANEL_STRIP_PRIVACY, privacy=True,
    )
    titles = [p.title for p in panels]
    assert titles == ["S0 quality", "S1b parsing mask", "S1 observed colors", "S3 atlas 64x64"]
```

In `tests/test_backend.py`:

```python
def test_generate_steps_use_privacy_panels(monkeypatch):
    from skinmaker import debugview as DV

    seen = {}
    real = DV.steps_sheets

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(DV, "steps_sheets", spy)
    with PHOTO.open("rb") as f:
        r = client().post(
            "/api/v1/generate-skin",
            files={"file": ("m.jpg", f, "image/jpeg")},
            data={"steps": "1"},
        )
    assert r.status_code == 200, r.text
    assert seen.get("privacy") is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_debugview.py::test_privacy_steps_skip_photo_panels tests/test_debugview.py::test_privacy_panel_set_has_no_photo_titles tests/test_backend.py::test_generate_steps_use_privacy_panels -v`
Expected: FAIL with `TypeError` for the unknown `privacy` keyword or missing panel names.

- [ ] **Step 3: Implement the privacy panels**

In `skinmaker/debugview.py`, add after `panel_s1`/`panel_mask`:

- `panel_quality(photo)`: create a neutral `Image.new("RGB", (PANEL_W, 110), BG)`; draw the same metrics as `panel_s0` (`face w×h`, `score`, `flags`, `bright`, `sharp`, `sat`, `hair`, `skin`, `bands`, `source`). For `photo.face is None`, note `REJECTED: no face detected`.
- `panel_mask_silhouette(seg)`: return `None` if `seg` is `None`; build an RGB array filled with `BG`, assign each `MASK_COLORS` class, return `Panel("S1b parsing mask", Image.fromarray(...), parts)` using the same percentage note as `panel_mask`.
- `panel_swatches(observed)`: a neutral panel with one row per `skin`, `hair`, `top`, `bottom`; each row is `_swatch(sample.rgb)`, `sample.hex`/`--`, `share=...`, `confident`/`low`, and `_share_bar(...)`. Reuse `_s1_note(observed)` for the note. No `photo.image` access.

Add the two privacy tuples next to `PANELS`/`PANEL_STRIP`.

Update `steps_sheets`:

```python
def steps_sheets(..., privacy: bool = False):
    strip = PANEL_STRIP_PRIVACY if privacy else PANEL_STRIP
    full = PANELS_PRIVACY if privacy else PANELS
    clean = contact_sheet(build_panels(photo, skin, model, observed, which=strip, seg=seg, privacy=privacy), columns=2)
    full = contact_sheet(build_panels(photo, skin, model, observed, which=full, seg=seg, privacy=privacy), columns=2)
```

Update `build_panels` signature with `privacy: bool = False` and add:

```python
elif name == "quality":
    out.append(panel_quality(photo))
elif name == "mask":
    p = panel_mask_silhouette(seg) if privacy else panel_mask(photo, seg)
    if p is not None:
        out.append(p)
elif name == "swatches" and observed is not None:
    out.append(panel_swatches(observed))
```

Keep the existing `s0`, `s1`, `mask`, `atlas`, `uvmap`, `preview` branches for the CLI (default `privacy=False`).

- [ ] **Step 4: Wire the backend**

In `backend/app.py`, change the `steps_sheets` call to include `privacy=True`.

- [ ] **Step 5: Run the focused tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_debugview.py tests/test_backend.py -q`
Expected: PASS. The CLI `skinmaker/samples.py` still uses the default `privacy=False`, so its photo panels remain.

- [ ] **Step 6: Commit**

```bash
git add skinmaker/debugview.py backend/app.py tests/test_debugview.py tests/test_backend.py
git commit -m "fix: make public processing sheets photo-free"
```

---

### Task 4: Purge legacy photo artifacts

**Files:**
- Create: `scripts/purge_photo_artifacts.sh`
- Modify: `scripts/cleanup_static.sh`
- Test: `tests/test_cleanup.py` (new)

**Interfaces:**
- Produces: `scripts/purge_photo_artifacts.sh [--root DIR] --yes`. Deletes `backend/static/skins/input_*` (files only), all files under `backend/static/steps/`, and all files under `backend/private/inputs/`; keeps every other file under `backend/static/skins/`; prints removed counts. Without `--yes`, exits 2 and changes nothing.

- [ ] **Step 1: Write the failing test**

```python
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "purge_photo_artifacts.sh"

pytestmark = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="bash script (Linux/macOS only)",
)


def test_purge_removes_photo_artifacts_and_keeps_skins(tmp_path):
    skins = tmp_path / "backend" / "static" / "skins"
    steps = tmp_path / "backend" / "static" / "steps"
    inputs = tmp_path / "backend" / "private" / "inputs"
    for d in (skins, steps, inputs):
        d.mkdir(parents=True)
    (skins / "input_abc.jpg").write_bytes(b"photo")
    (skins / "abc_c1.png").write_bytes(b"skin")
    (steps / "abc_steps.png").write_bytes(b"sheet")
    (inputs / "abc.jpg").write_bytes(b"photo")

    r = subprocess.run(
        ["bash", str(SCRIPT), "--root", str(tmp_path), "--yes"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert not (skins / "input_abc.jpg").exists()
    assert (skins / "abc_c1.png").exists()
    assert not any(steps.iterdir())
    assert not any(inputs.iterdir())


def test_purge_refuses_without_yes(tmp_path):
    skins = tmp_path / "backend" / "static" / "skins"
    skins.mkdir(parents=True)
    (skins / "input_abc.jpg").write_bytes(b"photo")
    r = subprocess.run(
        ["bash", str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert (skins / "input_abc.jpg").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cleanup.py -v`
Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement the purge script**

```bash
#!/usr/bin/env bash
# Remove user source photos and the old photo-bearing steps sheets.
# Result skins are kept. Run once on the release clone after deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --root) ROOT="${2:?--root needs a directory}"; shift ;;
    *) echo "usage: $0 [--root DIR] --yes" >&2; exit 2 ;;
  esac
  shift
done
[ "$YES" = 1 ] || { echo "refusing to delete without --yes" >&2; exit 2; }

SKINS="$ROOT/backend/static/skins"
STEPS="$ROOT/backend/static/steps"
INPUTS="$ROOT/backend/private/inputs"

count_files() { [ -d "$1" ] && find "$1" -type f | wc -l || echo 0; }

before_skins="$(count_files "$SKINS")"
before_steps="$(count_files "$STEPS")"
before_inputs="$(count_files "$INPUTS")"

if [ -d "$SKINS" ]; then
  find "$SKINS" -maxdepth 1 -type f -name 'input_*' -delete
fi
if [ -d "$STEPS" ]; then
  find "$STEPS" -mindepth 1 -type f -delete
fi
if [ -d "$INPUTS" ]; then
  find "$INPUTS" -mindepth 1 -type f -delete
fi

echo "skins: removed $(( before_skins - $(count_files "$SKINS") )) legacy input file(s); $(count_files "$SKINS") result skin(s) kept"
echo "steps: removed $(( before_steps - $(count_files "$STEPS") )) file(s)"
echo "private inputs: removed $(( before_inputs - $(count_files "$INPUTS") )) file(s)"
```

- [ ] **Step 4: Add the cleanup safety net**

In `scripts/cleanup_static.sh`, after the `skins`/`steps` age loop, add:

```bash
skins_dir="$ROOT/backend/static/skins"
if [ -d "$skins_dir" ]; then
  before="$(find "$skins_dir" -maxdepth 1 -type f -name 'input_*' | wc -l)"
  find "$skins_dir" -maxdepth 1 -type f -name 'input_*' -delete
  after="$(find "$skins_dir" -maxdepth 1 -type f -name 'input_*' | wc -l)"
  echo "input_*: removed $(( before - after )) legacy upload(s) (all ages)"
fi
```

Keep the existing 14-day rules for generated skins and steps. The `private/inputs` loop can stay as a legacy fallback; after the purge it is empty.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cleanup.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/purge_photo_artifacts.sh scripts/cleanup_static.sh tests/test_cleanup.py
git commit -m "fix: purge legacy uploaded photos and photo steps"
```

---

### Task 5: Update the notice, verify, and open the PR

**Files:**
- Modify: `frontend/src/App.jsx:520-524` (footer)
- Modify: `README.md:82,126`
- Modify: `docs/deployment.md:200-201`
- Modify: `docs/handover.md` (append a session entry)
- Add: this plan and the spec already in the branch.

- [ ] **Step 1: Update the user-facing notice**

Footer:

```jsx
<small>공개 데모입니다. 민감한 사진은 올리지 마세요. 업로드한 사진은 서버에 저장되지 않습니다.</small>
```

README line 82: change “14일 보존” to “생성물 14일 보존” and state that the source photo is not retained. Line 126:

```markdown
타인 사진에는 초상권 동의가 필요합니다. 공개 데모로 배포할 경우 민감한 사진을 올리지 마세요 — 업로드한 사진은 변환 후 서버에 저장되지 않고, 생성된 스킨과 처리 과정 시트만 보존 기간 후 삭제됩니다.
```

`docs/deployment.md` lines 200-201:

```markdown
Generated skins are served under `/static/skins/*` and photo-free steps sheets at
`/static/steps/*`; both are covered by retention. Source photos are not stored.
```

Add the one-time purge command to `docs/deployment.md`:

```bash
cd /home/achi/Programming/skinmaker-release
./scripts/purge_photo_artifacts.sh --yes
```

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, exit 0. Do not pipe the full suite to `tail`.

- [ ] **Step 3: Run the frontend checks**

Run: `cd frontend && npm run lint && npm run build`
Expected: both exit 0 (the existing chunk-size warning is fine).

- [ ] **Step 4: Check whitespace and the diff**

Run: `git diff --check`
Expected: no output, exit 0.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/App.jsx README.md docs/deployment.md docs/handover.md \
  docs/superpowers/specs/2026-11-05-no-photo-retention-design.md \
  docs/superpowers/plans/2026-11-05-no-photo-retention.md
git commit -m "docs: state that original photos are not retained"
git push -u origin fix/no-photo-retention
gh pr create --title "fix: stop retaining uploaded photos" --body "..."
```

PR body must include: the leak description, the 2,559 input + 4,688 steps counts, the purge command and result, full pytest output, lint/build results, and the residual risks (Cloudflare cache, backups, root process access).

- [ ] **Step 6: After the merge deploys, purge the release clone**

```bash
cd /home/achi/Programming/skinmaker-release
git pull --ff-only
./scripts/purge_photo_artifacts.sh --yes
find backend/static/skins -maxdepth 1 -name 'input_*' | wc -l   # 0
find backend/static/steps -type f | wc -l                        # 0
```

Verify an old `input_*` URL and an old steps URL return 404. If Cloudflare still serves them from cache, purge the cache in the dashboard (no API token is configured).

- [ ] **Step 7: Update the handover**

Append a 2026-11-05 entry with: the change, the counts, the commands/results, the residual risks, and the fact that `feat/skin-owner-edit` still needs Task 6.

---

### Task 6: Clean `feat/skin-owner-edit` (separate branch, after Task 5 merges)

Do this on the existing `feat/skin-owner-edit` worktree, not on the hotfix branch.

**Files:**
- Modify: `backend/jobs.py` (remove `INPUTS_DIR`, `input_name`, `"input"` from the record)
- Modify: `backend/app.py` (remove the private input write, `job_input` route, and `input` payload fields)
- Modify: `frontend/src/App.jsx` (replace `inputPhoto` from the API with the browser's local object URL, or remove the original card)
- Test: `tests/test_backend.py`, `tests/test_skin_jobs_api.py`, `tests/test_jobs.py`

- [ ] **Step 1: Rebase on the new `origin/master`**

```bash
git fetch origin
git rebase origin/master
```

- [ ] **Step 2: Remove the private input storage and endpoint**

In `backend/jobs.py`, remove `INPUTS_DIR`, the `input_name` parameter from `create_record`, and the `"input": input_name` record field. In `backend/app.py`, remove `JOBS.INPUTS_DIR.mkdir(...)`, the `write_bytes(raw)`, the `GET /api/v1/jobs/{token}/input` route, and any `input` field in the job payload. Keep the job record, overlay, attributes, preview, and render endpoints.

- [ ] **Step 3: Use a local object URL for the original card**

In `frontend/src/App.jsx`, remove `inputPhoto`/`setInputPhoto` and `data.data.input`. Add an effect that creates `URL.createObjectURL(file)` for the selected `File`, revokes it on change/unmount, and render the result card from that URL. If the UX decision is to keep no original card, delete the card and its state instead.

- [ ] **Step 4: Update the tests and run the suite**

Remove the input-storage assertions (`test_upload_is_stored_with_extension...`) and the `/input` API tests. Run:

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run lint && npm run build
```

- [ ] **Step 5: Commit and open the owner-edit PR**

```bash
git add backend/app.py backend/jobs.py frontend/src/App.jsx tests/
git commit -m "fix: remove per-job input photo retention"
```

The owner-edit PR must state that it depends on the no-photo-retention hotfix and that it no longer stores or serves source photos.

---

## Self-review notes

- The hotfix (Tasks 1–5) ships independently and removes the public leak.
- The privacy panel unit test pins the “no photo panel” rule; the backend spy pins the `privacy=True` wiring; Task 6 pins the owner-edit branch.
- The purge test keeps a result skin beside an input file, so a broad `skins/*` deletion would fail.
- The `input` API key is removed in the same task that removes the write, so the frontend cannot request a missing URL.
