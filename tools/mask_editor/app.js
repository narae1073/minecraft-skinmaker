import { initViewer } from './viewer.js';

const $ = (s) => document.querySelector(s);
const state = {
  parts: null, part_faces: null, faces: null, dims: null, layers: null, maskable: null, masks: null,
  key: null, value: null, part: 'head', layer: 'L1', face: null,
  mode: 'paint', viewMode: 'final', mirror: false,
  painting3d: false, painting2d: false, stroke: 0, history: [],
};
let viewer = null;
let previewTimer = null;
let previewSeq = 0;

const maskName = () => `${state.key}.${state.value}`;
const curMask = () => ensureMask();
const dimsFor = (face) => state.dims[face] || [8, 8];
const gridFor = (face) => curMask()[state.layer][face];

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

async function boot() {
  const r = await fetch('/api/defaults?t=' + Date.now(), { cache: 'no-store' });
  const j = await r.json();
  state.parts = j.parts; state.part_faces = j.part_faces; state.faces = j.faces;
  state.dims = j.dims; state.layers = j.layers; state.maskable = j.maskable; state.masks = j.masks;
  state.key = Object.keys(state.maskable)[0];
  state.value = state.maskable[state.key][0];
  state.part = 'head';
  const headFaces = state.part_faces[state.part];
  state.face = `${state.part}.${headFaces.includes('front') ? 'front' : headFaces[0]}`;
  renderTabs(); renderAtlas();
  try {
    viewer = initViewer($('#viewer'));
    window.maskEditor.viewer = viewer;
    viewer.setEditableLayer(state.layer);
    bind3d(viewer);
  } catch (e) {
    console.error(e);
    $('#status').textContent = '3D 뷰어 초기화 실패(WebGL): ' + e.message + ' — 오른쪽 atlas로 편집 가능';
  }
  preview();
}

function renderTabs() {
  const kt = $('#kindTabs'); kt.innerHTML = '';
  for (const key of Object.keys(state.maskable)) {
    const b = document.createElement('button');
    b.textContent = key; b.dataset.key = key;
    b.onclick = () => setKey(key);
    kt.appendChild(b);
  }
  const vt = $('#valueTabs'); vt.innerHTML = '';
  for (const value of state.maskable[state.key]) {
    const b = document.createElement('button');
    b.textContent = value; b.dataset.value = value;
    b.onclick = () => setValue(value);
    vt.appendChild(b);
  }
  const pt = $('#partTabs'); pt.innerHTML = '';
  for (const part of state.parts) {
    const b = document.createElement('button');
    b.textContent = part; b.dataset.part = part;
    b.onclick = () => setPart(part);
    pt.appendChild(b);
  }
  const lt = $('#layerTabs'); lt.innerHTML = '';
  for (const l of state.layers) {
    const b = document.createElement('button');
    b.textContent = l; b.dataset.layer = l;
    b.onclick = () => setLayer(l);
    lt.appendChild(b);
  }
  const ft = $('#faceTabs'); ft.innerHTML = '';
  for (const f of state.part_faces[state.part]) {
    const face = `${state.part}.${f}`;
    const b = document.createElement('button');
    b.textContent = f; b.dataset.face = face;
    b.onclick = () => setFace(face);
    ft.appendChild(b);
  }
  syncTabs();
}

function syncTabs() {
  for (const b of document.querySelectorAll('#kindTabs button')) b.classList.toggle('active', b.dataset.key === state.key);
  for (const b of document.querySelectorAll('#valueTabs button')) b.classList.toggle('active', b.dataset.value === state.value);
  for (const b of document.querySelectorAll('#partTabs button')) b.classList.toggle('active', b.dataset.part === state.part);
  for (const b of document.querySelectorAll('#layerTabs button')) b.classList.toggle('active', b.dataset.layer === state.layer);
  for (const b of document.querySelectorAll('#faceTabs button')) b.classList.toggle('active', b.dataset.face === state.face);
  for (const b of document.querySelectorAll('#atlas .faceBlock')) b.classList.toggle('active', b.dataset.face === state.face);
}

function setKey(k) {
  if (state.key === k) return;
  state.key = k;
  state.value = state.maskable[k][0];
  renderTabs(); renderAtlas();
  if (viewer) viewer.setEditableLayer(state.layer);
  schedulePreview();
  status();
}

function setValue(v) {
  if (state.value === v) return;
  state.value = v;
  syncTabs(); renderAtlas();
  schedulePreview(); status();
}

function setPart(p) {
  if (state.part === p) return;
  state.part = p;
  if (!state.part_faces[p].includes(state.face.split('.', 2)[1])) {
    state.face = `${p}.${state.part_faces[p][0]}`;
  }
  renderTabs(); renderAtlas();
  status();
}

function setLayer(l) {
  if (state.layer === l) return;
  state.layer = l;
  syncTabs(); renderAtlas();
  if (viewer) viewer.setEditableLayer(l);
  status();
}

function setFace(f) {
  state.face = f;
  state.part = f.split('.', 2)[0];
  renderTabs();
  syncTabs(); status();
}

function status() {
  const cell = $('#status');
  if (cell) cell.textContent = `${state.part} / ${maskName()} / ${state.layer} / ${state.face} — ${state.mode === 'paint' ? '칠하기' : '지우개'}`;
}

function renderAtlas() {
  const el = $('#atlas'); el.innerHTML = '';
  for (const face of state.faces) {
    const [w, h] = dimsFor(face);
    const block = document.createElement('div');
    block.className = 'faceBlock' + (face === state.face ? ' active' : '');
    block.dataset.face = face;
    const label = document.createElement('div');
    label.className = 'faceLabel';
    label.textContent = face.replace('.', ' · ');
    block.appendChild(label);
    const gridEl = document.createElement('div');
    gridEl.className = 'faceGrid';
    gridEl.style.gridTemplateColumns = `repeat(${w}, 20px)`;
    const g = gridFor(face);
    for (let v = 0; v < h; v++) for (let u = 0; u < w; u++) {
      const c = document.createElement('div');
      c.className = 'cell' + (g[v][u] ? ' on' : '');
      c.dataset.face = face; c.dataset.u = u; c.dataset.v = v;
      gridEl.appendChild(c);
    }
    block.appendChild(gridEl);
    el.appendChild(block);
  }
  syncTabs();
}

function cellEl(face, u, v) {
  return document.querySelector(`#atlas .cell[data-face="${face}"][data-u="${u}"][data-v="${v}"]`);
}

function paintAt(face, u, v, value) {
  const [w, h] = dimsFor(face);
  const g = gridFor(face);
  if (!g || v < 0 || v >= h || u < 0 || u >= w) return;
  let changed = false;
  if (g[v][u] !== value) { g[v][u] = value; cellEl(face, u, v)?.classList.toggle('on', !!value); changed = true; }
  if (state.mirror) {
    const mu = w - 1 - u;
    if (g[v][mu] !== value) { g[v][mu] = value; cellEl(face, mu, v)?.classList.toggle('on', !!value); changed = true; }
  }
  if (changed && state.face !== face) { state.face = face; state.part = face.split('.', 2)[0]; renderTabs(); }
  if (changed) status();
}

function pushHistory() {
  state.history.push(JSON.stringify(state.masks));
  if (state.history.length > 50) state.history.shift();
}

function bind3d(v) {
  const canvas = document.querySelector('#viewer canvas');
  if (!canvas) return;
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const hit = v.pick(state.part, state.layer, e.clientX, e.clientY);
    if (!hit) return;
    state.painting3d = true;
    state.stroke = state.mode === 'erase' ? 0 : 1;
    pushHistory();
    if (hit.part !== state.part) { state.part = hit.part; renderTabs(); }
    paintAt(hit.face, hit.u, hit.v, state.stroke);
    try { canvas.setPointerCapture(e.pointerId); } catch {}
    e.preventDefault();
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!state.painting3d) return;
    const hit = v.pick(state.part, state.layer, e.clientX, e.clientY);
    if (hit) paintAt(hit.face, hit.u, hit.v, state.stroke);
  });
}

function endStroke() {
  if (!state.painting3d && !state.painting2d) return;
  state.painting3d = false; state.painting2d = false;
  schedulePreview();
}
window.addEventListener('pointerup', endStroke);
window.addEventListener('mouseup', endStroke);

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(preview, 280);
}

async function preview() {
  const seq = ++previewSeq;
  $('#status').textContent = '3D 갱신 중…';
  const r = await fetch('/api/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: state.key, value: state.value, masks: state.masks, mode: state.viewMode }),
  });
  const j = await r.json();
  if (seq !== previewSeq) return;
  if (j.skin) {
    if (viewer) viewer.setSkin(j.skin + '?t=' + Date.now());
    $('#skin').src = j.skin + '?t=' + Date.now();
  }
  status();
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

function setMode(m) {
  state.mode = m;
  $('#paintBtn').className = m === 'paint' ? 'active' : '';
  $('#eraseBtn').className = m === 'erase' ? 'active' : '';
  status();
}

function setViewMode(m) {
  state.viewMode = m;
  $('#hoodModeBtn').className = m === 'final' ? 'active' : '';
  $('#maskModeBtn').className = m === 'mask' ? 'active' : '';
  schedulePreview();
}

$('#atlas').addEventListener('mousedown', (e) => {
  const c = e.target.closest('.cell'); if (!c) return;
  e.preventDefault();
  state.painting2d = true;
  state.stroke = state.mode === 'erase' ? 0 : 1;
  pushHistory();
  const face = c.dataset.face;
  if (state.face !== face) { state.face = face; state.part = face.split('.', 2)[0]; renderTabs(); }
  paintAt(face, +c.dataset.u, +c.dataset.v, state.stroke);
});
$('#atlas').addEventListener('mousemove', (e) => {
  if (!state.painting2d) return;
  const c = e.target.closest('.cell');
  if (c) paintAt(c.dataset.face, +c.dataset.u, +c.dataset.v, state.stroke);
});

$('#paintBtn').onclick = () => setMode('paint');
$('#eraseBtn').onclick = () => setMode('erase');
$('#hoodModeBtn').onclick = () => setViewMode('final');
$('#maskModeBtn').onclick = () => setViewMode('mask');
$('#mirror').onchange = (e) => { state.mirror = e.target.checked; };
$('#undoBtn').onclick = () => {
  if (!state.history.length) return;
  state.masks = JSON.parse(state.history.pop());
  renderAtlas(); schedulePreview();
};
$('#clearBtn').onclick = () => {
  pushHistory();
  curMask()[state.layer][state.face] = blank(state.face);
  renderAtlas(); schedulePreview();
};
$('#fillBtn').onclick = () => {
  pushHistory();
  const [w, h] = dimsFor(state.face);
  curMask()[state.layer][state.face] = Array.from({ length: h }, () => Array(w).fill(1));
  renderAtlas(); schedulePreview();
};
$('#saveBtn').onclick = save;
window.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); $('#undoBtn').click(); }
});

window.maskEditor = { state, viewer: null };
boot();
