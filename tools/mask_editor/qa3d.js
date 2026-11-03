import { initViewer } from './viewer.js';

const params = new URLSearchParams(location.search);
const dataUrl = params.get('data') || '/out/qa3d/cases_draft.js';

function render(data) {
  document.getElementById('title').textContent = data.title || 'skinmaker QA — 3D';
  const cases = data.cases || [];
  const fails = cases.filter(c => c.problems && c.problems.length).length;
  const stats = document.getElementById('stats');
  stats.textContent = `${cases.length} cases · ${fails} failed · ${cases.length - fails} passed`;
  stats.style.color = fails ? '#f08a80' : '#9fd0a8';
  const grid = document.getElementById('grid');
  for (const c of cases) {
    const failed = !!(c.problems && c.problems.length);
    const cell = document.createElement('div');
    cell.className = 'cell ' + (failed ? 'fail' : 'pass');
    const view = document.createElement('div');
    view.className = 'view';
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = c.label || '';
    if (failed) {
      const p = document.createElement('div');
      p.className = 'failtxt';
      p.textContent = c.problems[0];
      label.appendChild(p);
    }
    cell.append(view, label);
    grid.appendChild(cell);
    const v = initViewer(view);
    v.setSkin(c.skin);
    // Show the back: the hood-up body-back regression is only visible there.
    v.camera.position.set(0.4, 1.15, -3.4);
    v.controls.target.set(0, 0.9, 0);
    v.controls.update();
  }
  document.body.dataset.qa3dReady = '1';
}

const s = document.createElement('script');
s.src = dataUrl;
s.onload = () => render(window.QA3D || {});
s.onerror = () => { document.getElementById('stats').textContent = 'failed to load ' + dataUrl; };
document.head.appendChild(s);
