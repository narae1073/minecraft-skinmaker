# Results UI Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the loading-time hint and the candidate-card edit button, and make candidate cards visibly larger than the original-photo card.

**Architecture:** Delete the two unwanted UI elements and their now-unused CSS. Let CSS size the candidate 3D viewer through a new optional `className` prop, preserving the viewer's existing fixed-size API for the editor modal. The original photo stays `200×280`.

**Tech Stack:** React 19, Vite 8, plain CSS, three.js/React Three Fiber.

**Spec:** Approved design in the 2026-11-04 conversation: original stays `200×280`; candidate viewer becomes `약 258×357` on desktop; responsive on narrow screens.

## Global Constraints

- Original photo stays exactly `200×280` (`.input-photo`).
- Keep the sidebar `편집` button and the `SkinEditor` modal reachable.
- Keep the loading progress bar and `loading-stage` status line.
- Candidate viewer desktop size is `약 258×357` (13:18 ratio).
- No horizontal overflow at 360px viewport width; candidate remains larger than the original there.
- Never commit `frontend/dist/`, `node_modules/`, or generated screenshots.

## Review Focus

- 360px viewport: candidate card fits without horizontal scrolling and stays larger than the `200×280` original.
- Three candidates: desktop layout still wraps cleanly around the `300px`-wide candidate cards.
- `Skin3DViewer` without a `skinUrl` keeps a correctly sized empty state.
- `SkinEditor` still renders its viewer at `360×480` (no `className` path).
- Sidebar editing still opens `SkinEditor` after the candidate button is removed.

---

### Task 1: Remove the loading hint and candidate edit button

**Files:**
- Modify: `frontend/src/App.jsx:315-331` (loading overlay)
- Modify: `frontend/src/App.jsx:482-497` (candidate card actions)
- Modify: `frontend/src/App.css:848-852` (loading styles)

**Interfaces:**
- Consumes: existing `loadingPct`, `loadingStage`, `setEditorItem`, sidebar `edit-btn`.
- Produces: no new interfaces.

- [x] **Step 1: Delete the hint paragraph**

Remove `<p className="loading-hint">보통 20~40초 걸려요. 창을 닫지 말아 주세요.</p>` from the loading card. Keep the progress bar and `<p className="loading-stage">`.

> Later reverted by user request: the hint is restored as `보통 10초 정도 걸려요. 창을 닫지 말아 주세요.` (`.loading-hint` CSS restored). See `docs/handover.md`.

- [x] **Step 2: Delete the candidate edit button**

Remove only the `<button className="edit-btn" ...>스킨 편집 ✏️</button>` from the candidate card's `.card-actions`. Keep the download link and the sidebar edit button.

- [x] **Step 3: Delete the unused `.loading-hint` CSS rule**

Remove `.loading-hint { ... }` from `App.css`.

- [x] **Step 4: Verify**

Run: `cd frontend && npm run lint && npm run build`
Expected: both exit 0; the existing large-chunk warning is allowed.

- [x] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.css
git commit -m "fix: remove loading hint and candidate edit button"
```

---

### Task 2: Enlarge candidate cards with CSS-driven viewer sizing

**Files:**
- Modify: `frontend/src/components/Skin3DViewer.jsx:44-61`
- Modify: `frontend/src/App.jsx:483-488`
- Modify: `frontend/src/App.css:322-327` and the `max-width: 720px` media block

**Interfaces:**
- Consumes: `Skin3DViewer` existing props `{ skinUrl, model, width = 200, height = 300 }`.
- Produces: optional `className?: string` on `Skin3DViewer`; when present, CSS controls the wrapper size and inline width/height are omitted.

- [x] **Step 1: Add the optional class hook to the viewer**

In `Skin3DViewer`, accept `className`, build `skin-viewer ${className}`, and apply inline `{ width, height }` only when `className` is absent. Use the same class on the no-`skinUrl` fallback. Move the static background/radius into `.skin-viewer` CSS.

- [x] **Step 2: Give candidate cards a size contract**

Add `candidate-card` to the candidate `<div className="skin-card ...">` and render `<Skin3DViewer className="candidate-viewer" ... />` (no width/height props).

- [x] **Step 3: Add the sizing CSS**

Add:

```css
.skin-viewer { background: #e2e8f0; border-radius: 8px; }
.compare-grid .candidate-card { width: min(300px, 100%); }
.candidate-viewer { width: 100%; aspect-ratio: 13 / 18; }
```

Inside `@media (max-width: 720px)`, reduce only the candidate card padding to `10px` so the viewer stays larger than the `200×280` original at a 360px viewport.

- [x] **Step 4: Verify the build and rendered layout**

Run: `cd frontend && npm run lint && npm run build`
Expected: both exit 0.

Run the app with a mock backend and inspect at 1440px and 360px widths:
- loading overlay shows the bar + stage line, no hint;
- candidate card has only `스킨 다운로드`, no edit button;
- candidate viewer is about `약 258×357` on desktop and larger than the original photo on mobile;
- no horizontal page scroll at 360px;
- sidebar `편집` still opens the editor modal.

- [x] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.css frontend/src/components/Skin3DViewer.jsx
git commit -m "feat: enlarge candidate cards"
```

---

### Task 3: Handoff evidence

**Files:**
- Modify: `docs/handover.md` (session note at the end)

- [x] **Step 1: Record commands, results, and risks**

Add one dated bullet with lint/build results, viewport checks, and any manual-check caveat.

- [x] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [x] **Step 3: Commit**

```bash
git add docs/handover.md
git commit -m "docs: record results UI cleanup"
```
