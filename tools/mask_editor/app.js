import { initViewer } from './viewer.js';
import { ATLAS, LAYER_STYLE, buildBoxes, boxAt, gridHasMask, bresenham, texelAt, drawAtlas } from './atlas.js';

const $ = (s) => document.querySelector(s);
const dimsFor = (face) => (state.dims && state.dims[face]) || [8, 8];
const state = {
  faces: null, dims: null, layers: null, maskable: null, masks: null,
  enums: null, defaults: null, models: null, combo: null, comboKeys: [], model: 'classic', defaultsCombo: null,
  effective: null, warnings: [], notice: '',
  boxes: [], atlasRects: null, slimRects: null, slimSubFaces: [], key: null, value: null, layer: 'L1', face: null,
  mode: 'paint', viewMode: 'final', source: 'draft', mirror: false,
  zoom: 8, hover: null,
  painting: false, painting3d: false, stroke: 0, last: null, baseImg: null,
  history: { undo: [], redo: [] }, showBase: true,
};
let viewer = null;
const COMBO_STORAGE = 'skinmaker.combo.v1';
const COMBO_PRESETS = [
  { label: 'hoodie · long', combo: { top_garment: 'hoodie', sleeve_len: 'long', hood: 'down',
    hair_style: 'long_wavy', hair_length: 'long', bottom_garment: 'jeans' } },
  { label: 'jacket · short', combo: { top_garment: 'jacket', inner_top: 'shirt', closure_type: 'open',
    collar_type: 'shirt', sleeve_len: 'long', hair_style: 'short', hair_length: 'short',
    bottom_garment: 'pants' } },
  { label: 'dress · very long', combo: { top_garment: 'dress', sleeve_len: 'none', bottom_garment: 'none',
    hair_style: 'long_straight', hair_length: 'very_long' } },
  { label: 'tee · bob', combo: { top_garment: 'tee', sleeve_len: 'short', bottom_garment: 'jeans',
    hair_style: 'bob', hair_length: 'medium' } },
];

const maskName = () => `${state.key}.${state.value}`;
const curMask = () => ensureMask();
const gridFor = (face, layer = state.layer) => curMask()[layer][face];

function blank(face) { const [w, h] = dimsFor(face); return Array.from({ length: h }, () => Array(w).fill(0)); }

function ensureMask() {
  if (!state.masks[state.key + '.' + state.value]) {
    state.masks[state.key + '.' + state.value] = { L1: {}, L2: {} };
  }
  const m = state.masks[state.key + '.' + state.value];
  for (const layer of state.layers) {
    if (!m[layer]) m[layer] = {};
    for (const face of state.faces) {
      if (!m[layer][face]) m[layer][face] = blank(face);
    }
  }
  return m;
}

function defaultCombo() {
  return { ...(state.defaultsCombo || {}) };
}

function sanitizeCombo(raw) {
  const combo = defaultCombo();
  for (const key of state.comboKeys) {
    const value = raw && raw[key];
    if (state.enums && state.enums[key] && state.enums[key].includes(value)) combo[key] = value;
  }
  return combo;
}

function loadCombo() {
  let model = 'classic';
  try {
    const hash = new URLSearchParams(location.hash.replace(/^#/, ''));
    if (hash.get('v') === '1') {
      const raw = Object.fromEntries(state.comboKeys.map((key) => [key, hash.get(key)]));
      const m = hash.get('model');
      if (state.models && state.models.includes(m)) model = m;
      return { combo: sanitizeCombo(raw), model };
    }
  } catch {}
  try {
    const raw = JSON.parse(localStorage.getItem(COMBO_STORAGE) || 'null');
    if (raw && raw.v === 1) {
      if (state.models && state.models.includes(raw.model)) model = raw.model;
      return { combo: sanitizeCombo(raw.combo || {}), model };
    }
  } catch {}
  return { combo: defaultCombo(), model };
}

function saveCombo() {
  if (!state.combo) return;
  const params = new URLSearchParams({ v: '1', model: state.model });
  for (const key of state.comboKeys) params.set(key, state.combo[key]);
  try { history.replaceState(null, '', '#' + params.toString()); } catch {}
  try {
    localStorage.setItem(COMBO_STORAGE, JSON.stringify({ v: 1, model: state.model, combo: state.combo }));
  } catch {}
}

function syncComboUI() {
  for (const sel of document.querySelectorAll('#comboGrid select[data-combo]')) {
    if (state.combo) sel.value = state.combo[sel.dataset.combo];
  }
  const model = document.querySelector('#comboModel');
  if (model) model.value = state.model;
  const status = document.querySelector('#comboStatus');
  if (status) status.textContent = `3D: ${state.model}` +
    (state.combo && state.combo.symmetry === 'asymmetric' ? ' · symmetry: metadata (no visual)' : '');
}

function setCombo(key, value) {
  if (!state.combo || !state.enums[key] || !state.enums[key].includes(value)) return;
  state.combo[key] = value;
  saveCombo(); syncComboUI(); schedulePreview();
}

function renderCombo() {
  const grid = document.querySelector('#comboGrid');
  if (!grid) return;
  grid.innerHTML = '';
  for (const key of state.comboKeys) {
    const item = document.createElement('label');
    item.className = 'comboItem';
    const name = document.createElement('span');
    name.textContent = key;
    const sel = document.createElement('select');
    sel.dataset.combo = key;
    for (const value of state.enums[key]) {
      const option = document.createElement('option');
      option.value = value; option.textContent = value;
      sel.append(option);
    }
    sel.onchange = () => setCombo(key, sel.value);
    item.append(name, sel);
    grid.append(item);
  }
  const model = document.querySelector('#comboModel');
  if (model) {
    model.innerHTML = '';
    for (const m of (state.models || ['classic'])) {
      const option = document.createElement('option');
      option.value = m; option.textContent = m;
      model.append(option);
    }
    model.onchange = () => {
      state.model = model.value;
      setModelView(state.model);
      if (viewer) viewer.setModel(state.model);
      saveCombo(); syncComboUI(); schedulePreview();
    };
  }
  const presets = document.querySelector('#comboPresets');
  if (presets) {
    presets.innerHTML = '';
    for (const preset of COMBO_PRESETS) {
      const button = document.createElement('button');
      button.textContent = preset.label;
      button.onclick = () => {
        state.combo = { ...defaultCombo(), ...preset.combo };
        saveCombo(); syncComboUI(); schedulePreview();
      };
      presets.append(button);
    }
  }
  const reset = document.querySelector('#comboReset');
  if (reset) reset.onclick = () => {
    state.combo = defaultCombo();
    state.model = 'classic';
    setModelView(state.model);
    if (viewer) viewer.setModel(state.model);
    saveCombo(); syncComboUI(); schedulePreview();
  };
  syncComboUI();
}


// ---- 2D atlas (canvas) -------------------------------------------------

const ZOOM_MIN = 2;
const ZOOM_MAX = 24;
const WHEEL_STEP = 40;          // accumulated deltaY per zoom step (trackpads send many small deltas)
const STROKE_THROTTLE_MS = 150;
const SCHEDULE_DEBOUNCE_MS = 200;
const HISTORY_MAX = 100;
let atlasCanvas = null;
let atlasCtx = null;
let drawQueued = false;
let overlayCanvas = null;
let overlayCtx = null;
let wheelAccum = 0;

function activeBox() {
  return state.boxes.find((b) => b.face === state.face && b.layer === state.layer) || null;
}

// Read grid for a box: the slim override when the box is a slim sub-face and
// one exists, else the classic grid (its extra columns are ignored by the box).
function readGrid(name, layer, face, sub) {
  const entry = state.masks?.[name];
  if (!entry) return null;
  if (sub === 'slim' && entry.slim?.[layer]?.[face]) return entry.slim[layer][face];
  return entry[layer]?.[face] || null;
}

function cellOn(box, u, v) {
  const grid = readGrid(maskName(), box.layer, box.face, box.sub);
  return !!(grid && grid[v] && grid[v][u]);
}

function hasMaskFor(box) {
  for (let v = 0; v < box.h; v++) for (let u = 0; u < box.w; u++) if (cellOn(box, u, v)) return true;
  return false;
}

// Switch the atlas between the classic and slim layouts.
function setModelView(model) {
  const slim = model === 'slim';
  state.boxes = buildBoxes(slim ? state.slimRects : state.atlasRects, slim ? state.slimSubFaces : null);
  if (!state.boxes.some((b) => b.face === state.face && b.layer === state.layer)) {
    const first = state.boxes.find((b) => b.layer === 'L1' && b.face === 'head.front') || state.boxes[0];
    state.layer = first.layer;
    state.face = first.face;
  }
  scheduleDraw(); updateStatus();
}

function scheduleDraw() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => { drawQueued = false; drawAtlasNow(); });
}

function drawAtlasNow() {
  if (!atlasCtx) return;
  const z = state.zoom;
  const size = ATLAS * z;
  if (atlasCanvas.width !== size) {
    atlasCanvas.width = size;
    atlasCanvas.height = size;
    atlasCanvas.style.width = `${size}px`;
    atlasCanvas.style.height = `${size}px`;
  }
  atlasCtx.imageSmoothingEnabled = false;
  drawAtlas(atlasCtx, {
    boxes: state.boxes, zoom: z, cellOn, hasMaskFor,
    activeBox: activeBox(), hover: state.hover,
    base: state.showBase && state.baseImg ? state.baseImg : null,
  });
  const zl = document.querySelector('#zoomLabel');
  if (zl) zl.textContent = `${z}×`;
}

// Zoom keeps the texel under the cursor fixed on screen (anchor = client point).
function setZoom(z, anchor = null) {
  const next = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(z)));
  if (next === state.zoom) return;
  const wrap = document.querySelector('#atlasWrap');
  let fx = null, fy = null;
  if (anchor && atlasCanvas) {
    const before = atlasCanvas.getBoundingClientRect();
    fx = (anchor.clientX - before.left) / state.zoom;
    fy = (anchor.clientY - before.top) / state.zoom;
  }
  state.zoom = next;
  drawAtlasNow();
  if (fx !== null && wrap) {
    const after = atlasCanvas.getBoundingClientRect();
    wrap.scrollLeft += (after.left + fx * next) - anchor.clientX;
    wrap.scrollTop += (after.top + fy * next) - anchor.clientY;
  }
}

function fitZoom() {
  const wrap = document.querySelector('#atlasWrap');
  const width = wrap ? wrap.clientWidth - 16 : ATLAS * 8;
  setZoom(Math.floor(width / ATLAS));
}

function updateStatus() {
  const cell = $('#status');
  if (!cell) return;
  const box = activeBox();
  let where = box ? `${box.layer} · ${box.face}` : '—';
  if (state.hover && box) {
    where += ` · (${state.hover.u - box.x}, ${state.hover.v - box.y})`;
  } else if (state.hover) {
    where += ` · atlas (${state.hover.u}, ${state.hover.v})`;
  }
  const notice = state.notice ? ` · ${state.notice}` : '';
  cell.textContent = `${maskName()} · ${where} — ${state.mode === 'paint' ? '칠하기' : '지우개'} (우클릭·Shift = 지우개) · model=${state.model}${notice}`;
}

// ---- history ---------------------------------------------------------------
// A command is either a set of cell changes (strokes, fill, clear) or a whole
// mask snapshot (seed and reset). Cell changes are small; snapshots are rare.

let txn = null;

function txnBegin() { if (!txn) txn = []; }

function txnCommit() {
  if (txn && txn.length) pushCommand({ type: 'cells', changes: txn });
  txn = null;
}

function pushCommand(cmd) {
  state.history.undo.push(cmd);
  if (state.history.undo.length > HISTORY_MAX) state.history.undo.shift();
  state.history.redo = [];
  historyChanged();
}

function applyCommand(cmd, forward) {
  if (cmd.type === 'snapshot') {
    state.masks = JSON.parse(forward ? cmd.after : cmd.before);
    return;
  }
  const list = forward ? cmd.changes : [...cmd.changes].reverse();
  for (const c of list) {
    const grid = ensureGrid(c.name, c.layer, c.face, c.sub, { w: c.w, h: c.h });
    grid[c.v][c.u] = forward ? c.to : c.from;
  }
}

function undo() {
  const cmd = state.history.undo.pop();
  if (!cmd) return;
  applyCommand(cmd, false);
  state.history.redo.push(cmd);
  historyChanged();
}

function redo() {
  const cmd = state.history.redo.pop();
  if (!cmd) return;
  applyCommand(cmd, true);
  state.history.undo.push(cmd);
  historyChanged();
}

function historyChanged() {
  $('#undoBtn').disabled = !state.history.undo.length;
  $('#redoBtn').disabled = !state.history.redo.length;
  scheduleDraw(); overlayPreview(); schedulePreview(0); updateStatus();
}

// Whole-mask change as one undoable command.
function snapshotChange(nextMasks, label) {
  const before = JSON.stringify(state.masks);
  state.masks = nextMasks;
  const after = JSON.stringify(state.masks);
  if (before !== after) pushCommand({ type: 'snapshot', before, after, label });
  else historyChanged();
}

// ---- painting ------------------------------------------------------------

// Grid for (name, layer, face). The slim sub-view creates its override on first
// touch, copied from the classic grid's columns, so the visible cells stay the same.
function ensureGrid(name, layer, face, sub = null, box = null) {
  if (!state.masks[name]) state.masks[name] = { L1: {}, L2: {} };
  const entry = state.masks[name];
  if (sub === 'slim') {
    if (!entry.slim) entry.slim = { L1: {}, L2: {} };
    if (!entry.slim[layer]) entry.slim[layer] = {};
    if (!entry.slim[layer][face]) {
      const base = readGrid(name, layer, face, null);
      const w = box ? box.w : 3;
      const h = box ? box.h : (base ? base.length : 12);
      entry.slim[layer][face] = Array.from({ length: h }, (_, v) =>
        Array.from({ length: w }, (_, u) => (base && base[v] && base[v][u] ? 1 : 0)));
    }
    return entry.slim[layer][face];
  }
  if (!entry[layer]) entry[layer] = {};
  if (!entry[layer][face]) entry[layer][face] = blank(face);
  return entry[layer][face];
}

// Set one cell of the current mask and record the change for undo.
function setCell(box, u, v, value) {
  if (u < 0 || v < 0 || u >= box.w || v >= box.h) return false;
  const name = maskName();
  const grid = ensureGrid(name, box.layer, box.face, box.sub || null, box);
  const from = grid[v][u];
  if (from === value) return false;
  grid[v][u] = value;
  if (txn) txn.push({ name, layer: box.layer, face: box.face, sub: box.sub || null,
                      w: box.w, h: box.h, u, v, from, to: value });
  return true;
}

// Set a cell and its mirror (inside the same face) when mirror is on.
function setLocal(box, u, v, value) {
  let changed = setCell(box, u, v, value);
  if (state.mirror) changed = setCell(box, box.w - 1 - u, v, value) || changed;
  return changed;
}

// Paint one atlas texel. The box under the texel decides the layer and face.
function paintTexel(U, V, value) {
  const box = boxAt(state.boxes, U, V);
  if (!box) return false;
  state.layer = box.layer;
  state.face = box.face;
  return setLocal(box, U - box.x, V - box.y, value);
}

// 3D hits are face-local already.
function paintFaceCell(face, layer, u, v, value) {
  const box = state.boxes.find((b) => b.face === face && b.layer === layer);
  if (!box) return false;
  state.layer = layer;
  state.face = face;
  return setLocal(box, u, v, value);
}

function beginStroke(U, V, erase) {
  if (!boxAt(state.boxes, U, V)) return false;
  state.stroke = erase ? 0 : 1;
  txnBegin();
  state.painting = true;
  state.last = [U, V];
  paintTexel(U, V, state.stroke);
  return true;
}

function extendStroke(U, V) {
  if (!state.painting || !state.last) return;
  const [lu, lv] = state.last;
  for (const [x, y] of bresenham(lu, lv, U, V)) paintTexel(x, y, state.stroke);
  state.last = [U, V];
}

function endStroke() {
  if (!state.painting && !state.painting3d) return;
  state.painting = false;
  state.painting3d = false;
  state.last = null;
  txnCommit();
  historyChanged();
}

// Paint changes: refresh the atlas now, the 3D overlay immediately, and the
// server render throttled while dragging.
function onMaskChanged({ live }) {
  scheduleDraw();
  updateStatus();
  overlayPreview();
  if (live) schedulePreview(STROKE_THROTTLE_MS, true);
  else schedulePreview(SCHEDULE_DEBOUNCE_MS);
}

// ---- instant 3D preview (client overlay on the last server render) --------

// Tint the masked texels of the active key/value on the last server render.
// Approximate on purpose: the exact render replaces it when the server answers.
function overlayPreview() {
  // The tint previews the draft on top of the last render; it means nothing
  // against the production asset, so it is off there.
  if (!viewer || state.viewMode !== 'final' || state.source !== 'draft' || !state.baseImg) return;
  if (!overlayCanvas) {
    overlayCanvas = document.createElement('canvas');
    overlayCanvas.width = ATLAS;
    overlayCanvas.height = ATLAS;
    overlayCtx = overlayCanvas.getContext('2d');
  }
  overlayCtx.imageSmoothingEnabled = false;
  overlayCtx.clearRect(0, 0, ATLAS, ATLAS);
  overlayCtx.drawImage(state.baseImg, 0, 0, ATLAS, ATLAS);
  for (const box of state.boxes) {
    overlayCtx.fillStyle = LAYER_STYLE[box.layer].tint;
    for (let v = 0; v < box.h; v++) {
      for (let u = 0; u < box.w; u++) {
        if (cellOn(box, u, v)) overlayCtx.fillRect(box.x + u, box.y + v, 1, 1);
      }
    }
  }
  viewer.setSkinCanvas(overlayCanvas);
}

// ---- server preview --------------------------------------------------------

let previewTimer = null;
let previewSeq = 0;

function schedulePreview(delay = SCHEDULE_DEBOUNCE_MS, throttle = false) {
  if (throttle) {
    if (!previewTimer) previewTimer = setTimeout(() => { previewTimer = null; preview(); }, delay);
    return;
  }
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => { previewTimer = null; preview(); }, delay);
}

async function preview() {
  const seq = ++previewSeq;
  const r = await fetch('/api/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ combo: state.combo, model: state.model, key: state.key, value: state.value,
                           masks: state.masks, mode: state.viewMode, source: state.source }),
  });
  const j = await r.json();
  if (seq !== previewSeq) return;
  if (!r.ok) {
    const warn = document.querySelector('#comboWarn');
    if (warn) warn.textContent = 'preview error: ' + (j.error || r.status);
    return;
  }
  if (j.effective) state.effective = j.effective;
  if (j.warnings) {
    state.warnings = j.warnings;
    const warn = document.querySelector('#comboWarn');
    if (warn) warn.textContent = j.warnings.length ? ('⚠ ' + j.warnings.slice(0, 4).join(' · ')) : '';
  }
  if (j.skin) {
    const stamp = Date.now();
    const finalUrl = j.skin + '?t=' + stamp;
    // The base skin is always the final render, even in Mask view.
    const img = new Image();
    img.onload = () => {
      if (seq !== previewSeq) return;
      state.baseImg = img;
      scheduleDraw();
    };
    img.src = finalUrl;
    if (viewer) viewer.setSkin(j.mask ? j.mask + '?t=' + stamp : finalUrl);
    $('#skin').src = finalUrl;
  }
  updateStatus();
}

// ---- UI wiring -------------------------------------------------------------

function renderKeyTabs() {
  const kt = $('#kindTabs'); kt.innerHTML = '';
  for (const key of Object.keys(state.maskable)) {
    const b = document.createElement('button');
    b.textContent = key; b.dataset.key = key;
    b.onclick = () => setKey(key);
    kt.appendChild(b);
  }
  renderValueTabs();
}

function renderValueTabs() {
  const vt = $('#valueTabs'); vt.innerHTML = '';
  for (const value of state.maskable[state.key]) {
    const b = document.createElement('button');
    b.textContent = value; b.dataset.value = value;
    b.onclick = () => setValue(value);
    vt.appendChild(b);
  }
  syncTabs();
}

function syncTabs() {
  for (const b of document.querySelectorAll('#kindTabs button')) b.classList.toggle('active', b.dataset.key === state.key);
  for (const b of document.querySelectorAll('#valueTabs button')) b.classList.toggle('active', b.dataset.value === state.value);
}

function setKey(k) {
  if (state.key === k) return;
  state.key = k;
  state.value = state.maskable[k][0];
  if (state.combo && state.enums[k] && state.enums[k].includes(state.value)) {
    state.combo[k] = state.value; saveCombo(); syncComboUI();
  }
  renderKeyTabs();
  if (viewer) viewer.setEditableLayer(LAYERS_3D);
  scheduleDraw(); overlayPreview(); schedulePreview(); updateStatus();
}

function setValue(v) {
  if (state.value === v) return;
  state.value = v;
  if (state.combo && state.enums[state.key] && state.enums[state.key].includes(v)) {
    state.combo[state.key] = v; saveCombo(); syncComboUI();
  }
  syncTabs(); scheduleDraw(); overlayPreview(); schedulePreview(); updateStatus();
}

function setMode(m) {
  state.mode = m;
  $('#paintBtn').className = m === 'paint' ? 'active' : '';
  $('#eraseBtn').className = m === 'erase' ? 'active' : '';
  updateStatus();
}

function setViewMode(m) {
  state.viewMode = m;
  $('#hoodModeBtn').className = m === 'final' ? 'active' : '';
  $('#maskModeBtn').className = m === 'mask' ? 'active' : '';
  schedulePreview(0);
}

function setSource(src) {
  state.source = src;
  $('#srcBtn').textContent = src === 'draft' ? 'Draft' : 'Production';
  $('#srcBtn').className = src === 'production' ? 'active' : '';
  scheduleDraw(); overlayPreview(); schedulePreview(0); updateStatus();
}

function showPhoto(info) {
  $('#photoName').textContent = info ? info.name : '기본 fixture';
  $('#photoClear').disabled = !info;
}

// Upload a photo: its colours and hair silhouette drive the seeds and the preview.
// Existing drafts are kept; 초기 상태로 / 이 값만 seed로 re-seed from the photo.
async function uploadPhoto(file) {
  const fd = new FormData();
  fd.append('file', file, file.name);
  state.notice = '사진 분석 중… (처음에는 몇 초 걸려요)';
  updateStatus();
  const r = await fetch('/api/photo', { method: 'POST', body: fd });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const why = { no_face: '얼굴을 찾지 못했어요', bad_size: '파일이 너무 커요(15MB 이하)',
                  not_an_image: '이미지가 아니에요', unsupported_format: 'JPEG/PNG/WEBP 만 지원해요' }[j.error] || j.error || r.status;
    state.notice = '사진 실패: ' + why;
    updateStatus();
    return;
  }
  showPhoto(j);
  state.notice = `사진 적용: ${j.name} — '초기 상태로'를 누르면 seed 도 이 사진 기준 (Undo 가능)`;
  updateStatus();
  schedulePreview(0);
}

async function clearPhoto() {
  await fetch('/api/photo', { method: 'DELETE' });
  showPhoto(null);
  state.notice = '사진 해제 — 기본 fixture 기준';
  updateStatus();
  schedulePreview(0);
}

function setShowBase(on) {
  state.showBase = on;
  $('#baseBtn').className = on ? 'active' : '';
  scheduleDraw();
}

// Both layers are always shown in 3D so the overlay shell matches the output.
const LAYERS_3D = ['L1', 'L2'];

function bind2d() {
  atlasCanvas = $('#atlasCanvas');
  atlasCtx = atlasCanvas.getContext('2d');
  const texel = (e) => texelAt(e.clientX, e.clientY, atlasCanvas.getBoundingClientRect(), state.zoom);
  atlasCanvas.addEventListener('contextmenu', (e) => e.preventDefault());
  atlasCanvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 && e.button !== 2) return;
    const t = texel(e);
    if (!t) return;
    e.preventDefault();
    const erase = e.button === 2 || e.shiftKey || state.mode === 'erase';
    if (!beginStroke(t.u, t.v, erase)) return;
    atlasCanvas.setPointerCapture(e.pointerId);
    scheduleDraw(); updateStatus(); overlayPreview();
    schedulePreview(STROKE_THROTTLE_MS, true);
  });
  atlasCanvas.addEventListener('pointermove', (e) => {
    const t = texel(e);
    state.hover = t;
    if (state.painting && t) {
      extendStroke(t.u, t.v);
      onMaskChanged({ live: true });
    } else {
      scheduleDraw(); updateStatus();
    }
  });
  atlasCanvas.addEventListener('pointerleave', () => {
    if (!state.painting) { state.hover = null; scheduleDraw(); updateStatus(); }
  });
  const wrap = $('#atlasWrap');
  wrap.addEventListener('wheel', (e) => {
    e.preventDefault();
    wheelAccum += e.deltaY;
    if (Math.abs(wheelAccum) < WHEEL_STEP) return;
    const step = wheelAccum < 0 ? 1 : -1;
    wheelAccum = 0;
    setZoom(state.zoom + step, { clientX: e.clientX, clientY: e.clientY });
  }, { passive: false });
  $('#zoomIn').onclick = () => setZoom(state.zoom + 1);
  $('#zoomOut').onclick = () => setZoom(state.zoom - 1);
  $('#zoomFit').onclick = fitZoom;
}

function bind3d(v) {
  const canvas = document.querySelector('#viewer canvas');
  if (!canvas) return;
  const hitAt = (e) => v.pickAny(state.layer, e.clientX, e.clientY);
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const hit = hitAt(e);
    if (!hit) return;
    state.painting3d = true;
    state.stroke = (state.mode === 'erase' || e.shiftKey) ? 0 : 1;
    txnBegin();
    paintFaceCell(hit.face, state.layer, hit.u, hit.v, state.stroke);
    try { canvas.setPointerCapture(e.pointerId); } catch {}
    e.preventDefault();
    onMaskChanged({ live: true });
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!state.painting3d) return;
    const hit = hitAt(e);
    if (hit && paintFaceCell(hit.face, state.layer, hit.u, hit.v, state.stroke)) onMaskChanged({ live: true });
  });
}

// Clear / fill act on the active box and are one undo step.
function actOnActiveBox(fn) {
  const box = activeBox();
  if (!box) return;
  txnBegin();
  fn(box);
  txnCommit();
  historyChanged();
}

async function save() {
  $('#status').textContent = '저장 중…';
  const r = await fetch('/api/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ masks: state.masks }),
  });
  const j = await r.json();
  $('#status').textContent = j.ok ? `저장됨: ${j.path}` : '저장 실패';
}

// Reset every mask to the procedural seed. Combo settings are not touched.
async function resetToSeed() {
  const btn = $('#resetBtn');
  btn.disabled = true;
  $('#status').textContent = '초기 상태(seed) 계산 중…';
  try {
    const r = await fetch('/api/seed-all', { cache: 'no-store' });
    const j = await r.json();
    snapshotChange(j.masks, 'reset');
    $('#status').textContent = '초기 상태(procedural seed)로 되돌림 — Undo로 취소 가능';
  } finally {
    btn.disabled = false;
  }
}

function bindButtons() {
  $('#baseBtn').onclick = () => setShowBase(!state.showBase);
  $('#srcBtn').onclick = () => setSource(state.source === 'draft' ? 'production' : 'draft');
  $('#photoInput').onchange = (e) => { const f = e.target.files && e.target.files[0]; if (f) uploadPhoto(f); e.target.value = ''; };
  $('#photoClear').onclick = clearPhoto;
  $('#paintBtn').onclick = () => setMode('paint');
  $('#eraseBtn').onclick = () => setMode('erase');
  $('#hoodModeBtn').onclick = () => setViewMode('final');
  $('#maskModeBtn').onclick = () => setViewMode('mask');
  $('#mirror').onchange = (e) => { state.mirror = e.target.checked; };
  $('#undoBtn').onclick = undo;
  $('#redoBtn').onclick = redo;
  $('#resetBtn').onclick = resetToSeed;
  $('#clearBtn').onclick = () => actOnActiveBox((box) => {
    for (let v = 0; v < box.h; v++) for (let u = 0; u < box.w; u++) setCell(box, u, v, 0);
  });
  $('#fillBtn').onclick = () => actOnActiveBox((box) => {
    for (let v = 0; v < box.h; v++) for (let u = 0; u < box.w; u++) setCell(box, u, v, 1);
  });
  $('#saveBtn').onclick = save;
  $('#seedBtn').onclick = async () => {
    const r = await fetch(`/api/seed?key=${encodeURIComponent(state.key)}&value=${encodeURIComponent(state.value)}`);
    const j = await r.json();
    if (!j.mask) return;
    const next = { ...state.masks, [state.key + '.' + state.value]: j.mask };
    snapshotChange(next, 'seed');
    $('#status').textContent = `seed 복원: ${state.key}.${state.value} — Undo로 취소 가능`;
  };
}

window.addEventListener('pointerup', endStroke);
window.addEventListener('mouseup', endStroke);
window.addEventListener('keydown', (e) => {
  if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
  const mod = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
  else if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); redo(); }
  else if (mod && k === 's') { e.preventDefault(); save(); }
  else if (!mod && (e.key === '+' || e.key === '=')) setZoom(state.zoom + 1);
  else if (!mod && (e.key === '-' || e.key === '_')) setZoom(state.zoom - 1);
});

async function boot() {
  const r = await fetch('/api/defaults?t=' + Date.now(), { cache: 'no-store' });
  const j = await r.json();
  state.faces = j.faces; state.dims = j.dims; state.layers = j.layers;
  state.maskable = j.maskable; state.masks = j.masks;
  state.enums = j.enums || {}; state.defaults = j.defaults || {};
  state.models = j.models || ['classic']; state.defaultsCombo = j.combo || {};
  state.comboKeys = Object.keys(state.enums);
  state.atlasRects = j.atlas.rects;
  state.slimRects = j.slim.atlas.rects;
  state.slimSubFaces = j.slim.sub_faces;
  const loaded = loadCombo();
  state.combo = loaded.combo; state.model = loaded.model;
  setModelView(state.model);
  state.key = Object.keys(state.maskable)[0];
  state.value = state.maskable[state.key][0];
  const first = state.boxes.find((b) => b.layer === 'L1' && b.face === 'head.front') || state.boxes[0];
  state.layer = first.layer;
  state.face = first.face;
  renderCombo(); renderKeyTabs(); bind2d(); bindButtons();
  setShowBase(true);
  historyChanged();
  fetch('/api/photo', { cache: 'no-store' }).then((r) => r.json()).then(showPhoto).catch(() => {});
  fitZoom();
  scheduleDraw();
  try {
    viewer = initViewer($('#viewer'));
    window.maskEditor.viewer = viewer;
    viewer.setModel(state.model);
    viewer.setEditableLayer(LAYERS_3D);
    bind3d(viewer);
  } catch (e) {
    console.error(e);
    $('#status').textContent = '3D 뷰어 초기화 실패(WebGL): ' + e.message + ' — 2D atlas로 편집 가능';
  }
  schedulePreview(0);
}

window.maskEditor = { state, viewer: null, setCombo, saveCombo, loadCombo, renderCombo, paintTexel, drawAtlasNow, undo, redo };
boot();
