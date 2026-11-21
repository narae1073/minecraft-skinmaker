# Minecraft UI theme — design

**Date:** 2026-11-21
**Status:** approved approach; implementation in progress

## Intent

Make the public skin-maker page read as a Minecraft interface: a dark dirt-block
background, the classic gray beveled Minecraft button, a green primary action,
and a Korean-capable pixel font. The existing Minecraft wallpaper images go away.

## Goals

- Remove `frontend/public/wallpaper.png` and `wallpaper-mobile.png` (≈4.4 MB).
- Replace them with a small, dark, tileable dirt texture plus a pixel/block seam.
- Use one Korean pixel font across the UI, self-hosted (no external CDN).
- Theme every surface: container, upload panels, result cards, settings, chips,
  tables, sidebar, camera dialog, editor modal, crop modal, lightbox, loading.
- Keep the green conversion button prominent; secondary buttons are gray;
  destructive actions are red.
- Keep the current layout, copy, behaviour, API, and accessibility semantics.

## Non-goals

- No component rewrite, no Tailwind/CSS Modules, no JS behaviour changes.
- No new pixel-art illustrations or changes to the 3D viewer geometry.
- No changes to the backend, pipeline, or generated skin assets.
- No dark/light OS toggle: this UI is always dark.

## Anti-goals

- White cards left behind on the dark background (the "half-themed" result).
- Rounded corners, soft shadows, smooth gradients, or smooth spinners.
- A Latin-only pixel font with Hangul falling back to a system sans.
- Text that becomes unreadable on the dirt texture.

## Approaches considered

1. **Override layer** — add `minecraft.css` after `App.css` and override
   selectors. Fast and reversible, but duplicates every selector, invites
   specificity fights, and misses hover/disabled/focus states.
2. **Token refactor (chosen)** — define palette/font/bevel tokens and shared
   panel/button rules, then make the existing rules consume them. Larger diff,
   one source of truth, all components consistent.
3. **Rewrite with CSS Modules/Tailwind** — overkill for this repo's plain CSS
   and React components.

## Design decisions

### Palette

| Token | Value | Use |
|---|---|---|
| `--mc-bg` | `#14100c` | page base under the dirt tile |
| `--mc-panel` | `#241f1a` | main container |
| `--mc-panel-2` | `#2b2520` | nested panels/cards |
| `--mc-edge` | `#0b0907` | 2px borders and slots |
| `--mc-ink` | `#f4f0e8` | body text |
| `--mc-ink-dim` | `#c2b6a6` | secondary text |
| `--mc-ink-faint` | `#8f8272` | hints/meta |
| `--mc-gui` | `#6b6b6b` | default button |
| `--mc-gui-hover` | `#7f8a7f` | button hover |
| `--mc-gui-dark` | `#3f3f3f` | disabled button |
| `--mc-emerald` | `#3fbf6f` | primary hover/accent |
| `--mc-emerald-dark` | `#2f7d4f` | primary button |
| `--mc-gold` | `#f5d442` | focus/hover text, highlights |
| `--mc-danger` | `#a8433e` | destructive button |

Bevel recipe (Minecraft/seedle): `inset 2px 2px 0 rgba(255,255,255,.18)` and
`inset -2px -2px 0 rgba(0,0,0,.55)`; pressed inverts it. Border radius is 0.

### Typography

- **NeoDunggeunmo** (SIL OFL 1.1), self-hosted at
  `frontend/public/fonts/NeoDunggeunmo.woff2` (44 KB) with
  `NeoDunggeunmo-OFL.txt`.
- 16px grid: body/buttons/inputs 16px; `h2` 32px; `h1` 48px desktop /
  32px mobile. No synthetic bold (`font-synthesis: none`); emphasis comes from
  size, colour, and the `2px 2px` black text shadow.
- `-webkit-font-smoothing: none`, `text-rendering: optimizeSpeed`.

### Background

- New `frontend/public/dirt-dark.png`: deterministic 16×16 tile, 605 bytes.
- Repeated at 64px with `image-rendering: pixelated`, a hard 2px seam every
  64px, and a dark radial vignette. The same pattern is used on mobile (no
  separate mobile image).

### Components covered

`.container`, `.upload-panel`, `.selected-photo`, `.skin-card`, `.skin-viewer`,
`.category-panel`, `.config-section`, `.chips`/`.chip`, `.json-table`,
`.steps-thumb-btn`, `.steps-*`, `.sidebar`, `.skin-list-item`, `.editor-modal`,
`.camera-dialog`, `.crop-modal`, `.lightbox`, `.loading-overlay`, `.footer`,
`.mobile-site-qr`, and all ten button classes.

### Button hierarchy

- `.generate-btn` and `.download-btn`: green primary.
- `.camera-btn`, `.file-picker-btn`, `.edit-btn`, `.copy-json-btn`,
  `.steps-mode-btn`, `.sidebar-toggle-btn`, `.close-btn`: gray secondary.
- `.delete-btn`: red danger.
- Focus: 2px gold outline; active: inverted bevel; disabled: dark gray.

### Inputs

`select`, checkbox, range, and colour inputs get `appearance: none` where
needed, square slots, 2px black borders, and emerald checked/filled states.
Native focus outlines stay visible.

## Verification

- `.venv/bin/python -m pytest -q` (no Python changes, but the suite also reads
  frontend files).
- `cd frontend && npm run lint && npm run build`.
- Headless Chrome screenshots at 1440×1000 and 390×844; no horizontal scroll;
  check the config, result cards, sidebar, editor/crop overlays, and loading.
- `git check-ignore`/`git status` confirm the 4.4 MB wallpapers are deleted and
  only the 605-byte tile plus the 44 KB font are added.

## Risks

- Pixel fonts at non-grid sizes blur: keep 16/32/48 and avoid synthetic bold.
- Dark-on-dark contrast: panels stay opaque; body text uses `--mc-ink`.
- Native controls (range/checkbox/colour) vary by browser; verify Chrome and
  Firefox fallbacks.
- 16px minimum text may make dense areas taller; mobile at 360px needs a check.
- The dirt tile is decorative; it must never be the only contrast behind text.
