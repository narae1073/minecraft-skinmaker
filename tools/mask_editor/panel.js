// Shared "skin attributes" panel for both editors.
//
// The per-skin editor (/edit/{id}) and the developer mask editor show the same
// body-area groups. The panel only owns the DOM, the photo diff badges and the
// busy state; each editor supplies how to persist a change:
//
//   apply(body, label, meta) -> Promise<{ attributes?, hat_color?, overrides? }>
//
// where body is one of
//   { attributes: {...}, hat_color?, index? }   normal change
//   { reset: true, index? }                     every attribute back to photo
//   { reset_attributes: [key], index? }          one attribute back to photo

export const ATTR_LABELS = {
  top_garment: '상의', inner_top: '속셔츠', sleeve_len: '소매', closure_type: '여밈',
  collar_type: '칼라', pocket_type: '주머니', hood: '후드', hood_fit: '후드 핏',
  bottom_garment: '하의', hair_style: '머리 스타일', hair_length: '머리 길이',
  headwear: '모자', neckwear: '넥웨어', beard: '수염',
};

export const ATTR_TEXT = {
  top_garment: {
    tee: '티셔츠', hoodie: '후디', jacket: '재킷', shirt: '셔츠', sweater: '스웨터',
    vest: '조끼', uniform: '교복', apron: '앞치마', overalls: '멜빵', dress: '원피스',
    none: '없음',
  },
  inner_top: { none: '없음', shirt: '셔츠', tee: '티', knit: '니트' },
  sleeve_len: { none: '없음', short: '반팔', three_quarter: '7부', long: '긴팔' },
  closure_type: { none: '없음', zipper: '지퍼', buttons: '단추', open: '오픈' },
  collar_type: { none: '없음', crew: '크루', v_neck: '브이넥', shirt: '셔츠', hood: '후드' },
  pocket_type: { none: '없음', patch: '패치' },
  hood: { none: '없음', up: '올림', down: '내림' },
  hood_fit: { normal: '보통', shallow: '얕게', deep: '깊게' },
  bottom_garment: { jeans: '청바지', pants: '바지', shorts: '반바지', skirt: '스커트', none: '없음' },
  hair_style: {
    short: '숏', pixie: '픽시', bob: '보브', long_straight: '롱 스트레이트',
    long_wavy: '롱 웨이브', curly: '컬리', ponytail: '포니테일', bun: '번',
  },
  hair_length: { short: '숏', medium: '미디엄', long: '롱', very_long: '베리 롱' },
  headwear: { none: '없음', cap: 'cap', beanie: 'beanie' },
  neckwear: { none: '없음', tie: '타이' },
  beard: { none: '없음', stubble: '수염자국', full: '풀수염' },
};

export const ATTR_GROUPS = [
  { title: '상의', fields: ['top_garment', 'inner_top', 'sleeve_len', 'closure_type', 'collar_type', 'pocket_type', 'hood', 'hood_fit'] },
  { title: '하의', fields: ['bottom_garment'] },
  { title: '머리', fields: ['hair_style', 'hair_length'] },
  { title: '액세서리', fields: ['headwear', 'neckwear'] },
  { title: '얼굴', fields: ['beard'] },
];

export const ATTR_FIELDS = ATTR_GROUPS.flatMap((g) => g.fields);
export const HAT_DEFAULT = { cap: '#e9eef3', beanie: '#1f1f1f' };

const HAIR_SHORT_STYLES = new Set(['short', 'pixie']);
const HAIR_LONG_STYLES = new Set(['long_straight', 'long_wavy', 'ponytail', 'bun']);

export const attrText = (key, value) => (ATTR_TEXT[key] && ATTR_TEXT[key][value]) || value;

// Contradictory style/length pairs clip each other; advisory only.
export function hairWarning(style, length) {
  if ((HAIR_SHORT_STYLES.has(style) && (length === 'long' || length === 'very_long'))
      || (HAIR_LONG_STYLES.has(style) && length === 'short')) {
    return '머리 스타일과 길이가 맞지 않아 머리가 잘릴 수 있어요';
  }
  return '';
}

/**
 * Build the attributes panel.
 *
 * opts:
 *   enums, combo, maskable    editor state used to fill the selects
 *   photoCombo()              photo-estimate values for the diff badges
 *   overrides()               current attribute overrides (hat colour badge)
 *   hatColor()                current hat colour or null
 *   apply(body, label, meta)  persistence hook, see the header comment
 *   onMaskTarget(key, value, open)
 *   onChangeLocal(key, value) optional: called before apply (standalone preview)
 *   busyBefore()/busyAfter()  optional async hooks around apply (job saves masks)
 */
export function buildAttributesPanel(opts) {
  const panel = document.createElement('div');
  panel.className = 'group jobAttrs';
  panel.id = 'jobAttrPanel';

  const head = document.createElement('div');
  head.className = 'jobAttrHead';
  const title = document.createElement('span');
  title.className = 'gtitle';
  title.textContent = '스킨 속성';
  const changedLabel = document.createElement('span');
  changedLabel.className = 'hint jobAttrChanged';
  changedLabel.id = 'jobAttrChanged';
  changedLabel.setAttribute('role', 'status');
  head.append(title, changedLabel);
  panel.append(head);

  const selects = {};
  const rows = {};
  const groups = [];

  const makeSelect = (key) => {
    const sel = document.createElement('select');
    sel.dataset.attr = key;
    const enums = (opts.enums && opts.enums[key]) || [];
    for (const v of enums) {
      const o = document.createElement('option');
      o.value = v;
      o.textContent = attrText(key, v);
      sel.append(o);
    }
    sel.value = (opts.combo && opts.combo[key]) || enums[0] || 'none';
    return sel;
  };

  const makeRow = (key) => {
    const row = document.createElement('div');
    row.className = 'jobAttrRow';
    const label = document.createElement('div');
    label.className = 'jobAttrLabel';
    const name = document.createElement('span');
    name.className = 'jobAttrName';
    name.textContent = ATTR_LABELS[key] || key;
    const diff = document.createElement('span');
    diff.className = 'jobAttrDiff';
    label.append(name, diff);
    const controls = document.createElement('div');
    controls.className = 'jobAttrControls';
    const sel = makeSelect(key);
    const maskBtn = document.createElement('button');
    maskBtn.type = 'button';
    maskBtn.className = 'attrMaskBtn';
    maskBtn.textContent = '마스크';
    maskBtn.title = '이 값의 마스크를 칠합니다 (고급 섹션 열기)';
    maskBtn.onclick = () => opts.onMaskTarget(key, sel.value, true);
    const resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'attrResetBtn';
    resetBtn.textContent = '↩';
    resetBtn.title = '사진 추정값으로 되돌리기';
    resetBtn.setAttribute('aria-label', `${ATTR_LABELS[key] || key} 사진 추정값으로 되돌리기`);
    resetBtn.disabled = true;
    controls.append(sel, maskBtn, resetBtn);
    row.append(label, controls);
    selects[key] = sel;
    rows[key] = { row, diff, sel, resetBtn };
    return row;
  };

  for (const group of ATTR_GROUPS) {
    const details = document.createElement('details');
    details.className = 'attrGroup';
    details.open = true;
    const summary = document.createElement('summary');
    const summaryTitle = document.createElement('span');
    summaryTitle.textContent = group.title;
    const summaryCount = document.createElement('span');
    summaryCount.className = 'attrGroupCount';
    summary.append(summaryTitle, summaryCount);
    details.append(summary);
    for (const key of group.fields) {
      if (!(opts.enums && opts.enums[key])) continue;
      details.append(makeRow(key));
    }
    groups.push({ ...group, details, count: summaryCount });
    panel.append(details);
  }

  const color = document.createElement('input');
  color.type = 'color';
  color.id = 'jobHatColor';
  {
    const colorRow = document.createElement('div');
    colorRow.className = 'jobAttrRow jobAttrColorRow';
    const colorLabel = document.createElement('div');
    colorLabel.className = 'jobAttrLabel';
    const colorName = document.createElement('span');
    colorName.className = 'jobAttrName';
    colorName.textContent = '모자색';
    const colorDiff = document.createElement('span');
    colorDiff.className = 'jobAttrDiff';
    colorDiff.id = 'jobHatColorDiff';
    colorLabel.append(colorName, colorDiff);
    const colorControls = document.createElement('div');
    colorControls.className = 'jobAttrControls';
    color.value = opts.hatColor() || HAT_DEFAULT[selects.headwear.value] || '#e9eef3';
    color.disabled = selects.headwear.value === 'none';
    colorControls.append(color);
    colorRow.append(colorLabel, colorControls);
    groups.find((g) => g.title === '액세서리').details.append(colorRow);
  }
  const colorDiff = panel.querySelector('#jobHatColorDiff');

  const status = document.createElement('p');
  status.className = 'hint jobAttrStatus';
  status.id = 'jobAttrStatus';
  status.setAttribute('role', 'status');
  status.textContent = opts.statusHint || '사진에서 추정한 값 · 바꾸면 저장됩니다';
  panel.append(status);

  const actions = document.createElement('div');
  actions.className = 'jobAttrActions';
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.id = 'jobAttrReset';
  reset.textContent = '사진 추정값으로';
  actions.append(reset);
  panel.append(actions);

  const updateDiff = () => {
    const photo = opts.photoCombo() || {};
    let total = 0;
    for (const group of groups) {
      let count = 0;
      for (const key of group.fields) {
        const row = rows[key];
        if (!row) continue;
        const base = photo[key];
        const changed = Boolean(base) && row.sel.value !== base;
        row.row.classList.toggle('changed', changed);
        if (row.resetBtn) row.resetBtn.disabled = !changed;
        const photoText = attrText(key, base);
        row.diff.textContent = changed ? `사진: ${photoText}` : '';
        row.diff.title = changed ? `변경됨 · 사진 추정값: ${photoText}` : '';
        if (changed) count++;
      }
      group.count.textContent = count ? `${count} 변경` : '';
      group.count.classList.toggle('changed', count > 0);
      total += count;
    }
    if (colorDiff) {
      const overrides = opts.overrides() || {};
      colorDiff.textContent = Object.prototype.hasOwnProperty.call(overrides, 'hat_color') ? '변경됨' : '';
    }
    changedLabel.textContent = total ? `사진과 다른 속성 ${total}개` : '사진 추정값 그대로';
    changedLabel.classList.toggle('changed', total > 0);
  };

  const syncFrom = (attrs) => {
    if (!attrs) return;
    for (const key of ATTR_FIELDS) {
      if (attrs[key] && selects[key] && [...selects[key].options].some((o) => o.value === attrs[key])) {
        selects[key].value = attrs[key];
      }
    }
    color.disabled = selects.headwear.value === 'none';
    updateDiff();
  };

  let busy = false;

  const setBusy = (on) => {
    reset.disabled = on;
    for (const sel of Object.values(selects)) sel.disabled = on;
    for (const row of Object.values(rows)) if (row.resetBtn) row.resetBtn.disabled = on;
    color.disabled = on || selects.headwear.value === 'none';
  };

  const apply = async (body, label, meta = {}) => {
    if (busy) return;
    busy = true;
    setBusy(true);
    try {
      if (opts.busyBefore) await opts.busyBefore();
      const j = (await opts.apply(body, label, meta)) || {};
      syncFrom(j.attributes || currentAttributes());
      if (j.hat_color) color.value = j.hat_color;
      const warn = hairWarning(selects.hair_style.value, selects.hair_length.value);
      status.textContent = `${label} 저장됨${j.revision != null ? ` · revision ${j.revision}` : ''}${warn ? ' ⚠ ' + warn : ''}`;
      status.classList.toggle('warn', Boolean(warn));
      updateDiff();
    } catch (e) {
      status.textContent = '저장 실패: ' + e.message;
    } finally {
      setBusy(false);
      updateDiff();
      busy = false;
      if (opts.busyAfter) opts.busyAfter();
    }
  };

  const currentAttributes = () => {
    const attrs = {};
    for (const key of ATTR_FIELDS) if (selects[key]) attrs[key] = selects[key].value;
    return attrs;
  };

  const currentBody = () => {
    const body = { attributes: currentAttributes() };
    if (selects.headwear.value !== 'none') body.hat_color = color.value;
    return body;
  };

  for (const key of ATTR_FIELDS) {
    const sel = selects[key];
    if (!sel) continue;
    sel.onchange = () => {
      if (key === 'headwear') {
        color.disabled = sel.value === 'none';
        if (HAT_DEFAULT[sel.value] && !opts.hatColor()) color.value = HAT_DEFAULT[sel.value];
      }
      if (opts.onChangeLocal) opts.onChangeLocal(key, sel.value);
      if ((opts.maskable[key] || []).includes(sel.value)) opts.onMaskTarget(key, sel.value);
      updateDiff();
      apply(currentBody(), ATTR_LABELS[key], { kind: 'attributes', key });
    };
  }
  color.onchange = () => apply(currentBody(), '모자색', { kind: 'hat_color' });

  for (const [key, row] of Object.entries(rows)) {
    row.resetBtn.onclick = () => apply(
      { reset_attributes: [key] }, `${ATTR_LABELS[key] || key} 되돌림`, { kind: 'reset_key', key },
    );
  }

  reset.onclick = () => apply({ reset: true }, '사진 추정값', { kind: 'reset' });

  updateDiff();
  return {
    panel,
    selects,
    status,
    updateDiff,
    syncFrom,
    setStatus: (text, warn = false) => {
      status.textContent = text;
      status.classList.toggle('warn', Boolean(warn));
    },
    currentAttributes,
    currentBody,
    resetTabIndex: () => panel.querySelectorAll('select, button, input'),
  };
}
