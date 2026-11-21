# Minecraft UI theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the public skin-maker page as a Minecraft GUI with a dark dirt background, gray beveled buttons, a green primary action, and a Korean pixel font.

**Architecture:** A token refactor of the existing plain CSS. `index.css` owns palette/font/background/global typography; `App.css` component rules consume the tokens and shared bevel recipes. No JS behaviour changes.

**Tech Stack:** React 19, Vite 8, plain CSS, self-hosted WOFF2.

**Spec:** `docs/superpowers/specs/2026-11-21-minecraft-theme-design.md`

## Global Constraints

- Delete `frontend/public/wallpaper.png` and `frontend/public/wallpaper-mobile.png`.
- Font: NeoDunggeunmo only; sizes 16/32/48; no synthetic bold.
- Border radius: 0; bevel: `inset 2px 2px` light + `inset -2px -2px` dark.
- Primary = `#2f7d4f`; secondary = `#6b6b6b`; danger = `#a8433e`; accent = `#3fbf6f`/`#f5d442`.
- No API, pipeline, copy, or layout behaviour changes.

## Review Focus

- Body text over the dirt tile must stay readable (panels are opaque).
- 16px pixel text in dense rows must not overflow at 360px.
- Native range/checkbox/colour controls must remain usable and visible.
- Hover/active/disabled/focus states must exist for every button.
- Font fallback must not silently replace Hangul with a smooth sans.

---

### Task 1: Theme assets

**Files:**
- Create: `frontend/public/fonts/NeoDunggeunmo.woff2`
- Create: `frontend/public/fonts/NeoDunggeunmo-OFL.txt`
- Create: `frontend/public/dirt-dark.png`
- Delete: `frontend/public/wallpaper.png`, `frontend/public/wallpaper-mobile.png`

- [ ] Download the 44 KB NeoDunggeunmo WOFF2 and OFL text; verify `file` reports WOFF2.
- [ ] Generate the deterministic 16×16 dirt tile; keep it under 1 KB.
- [ ] Delete both wallpapers and confirm no `wallpaper` reference remains.

### Task 2: Tokens, font, background, global typography

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.css:1-100`

- [ ] Add `@font-face` for NeoDunggeunmo.
- [ ] Add the palette/bevel/font tokens on `:root`; set `color-scheme: dark`, `font-size: 16px`, `font-synthesis: none`.
- [ ] Replace the wallpaper with the dirt tile, 64px seam grid, and vignette; use one pattern for all widths.
- [ ] Set base body/heading/link/selection/scrollbar/focus styles.
- [ ] Verify `npm run build` and inspect the background screenshot.

### Task 3: Panels and typography surfaces

**Files:**
- Modify: `frontend/src/App.css` (container, upload, cards, analysis, steps, config, sidebar, overlays)

- [ ] Apply the panel recipe (panel background, 2px edge, bevel, radius 0) to every surface listed in the spec.
- [ ] Replace light text colours with `--mc-ink`/`--mc-ink-dim`/`--mc-ink-faint`; links and summaries use gold/emerald.
- [ ] Keep the main container≥0.94 opaque so body text never sits directly on the tile.
- [ ] Verify desktop and mobile screenshots.

### Task 4: Buttons and controls

**Files:**
- Modify: `frontend/src/App.css` (button base + ten classes, inputs, selects, checkbox, range, colour)

- [ ] Add one MC button base for `button`/`.download-btn`; add green primary, gray secondary, red danger, pressed/disabled/focus states.
- [ ] Restyle select/checkbox/range/colour with square slots and emerald fills; keep native focus visible.
- [ ] Verify every button state in a style harness or the running page.

### Task 5: Overlays, loading, lightbox, camera/crop dialogs

**Files:**
- Modify: `frontend/src/App.css` (loading, editor, crop, lightbox, camera dialog)

- [ ] Theme all overlays/dialogs with panels and dark backdrops.
- [ ] Convert the loading bar to hard segments and the spinner to a stepped square.
- [ ] Verify Escape/close buttons remain visible and keyboard focus is kept.

### Task 6: Responsive and accessibility pass

**Files:**
- Modify: `frontend/src/App.css` media queries

- [ ] Remove the mobile wallpaper rule; adjust heading sizes/padding at ≤720px.
- [ ] Check 1440×1000 and 390×844/360×800: no horizontal scroll, no clipped buttons.
- [ ] Confirm 2px gold focus rings, contrast, and reduced-motion compatibility.

### Task 7: Verification, docs, PR

- [ ] `cd frontend && npm run lint && npm run build`.
- [ ] `.venv/bin/python -m pytest -q` (frontend-reading tests included).
- [ ] Capture desktop/mobile screenshots into `out/theme/` (gitignored).
- [ ] Update `docs/handover.md` with the theme change, assets, and risks.
- [ ] Commit on `feat/minecraft-theme`, push, open a PR, admin-merge after green CI.
