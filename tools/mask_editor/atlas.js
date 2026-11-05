// Pure helpers for the 2D atlas editor. Nothing here touches the DOM except
// drawAtlas(), which only uses the 2D context it is given.

export const ATLAS = 64;

// L1 = base layer, L2 = overlay layer. Distinct hatch direction AND colour so
// the layer you are painting on is obvious even at a glance.
export const LAYER_STYLE = {
  L1: { base: '#c9d6e6', line: '#1d4ed8', tint: 'rgba(29, 78, 216, 0.22)', hatch: 'backslash' },
  L2: { base: '#f2dcc0', line: '#c2410c', tint: 'rgba(194, 65, 12, 0.22)', hatch: 'slash' },
};

// Dimmed boxes (no mask pixels) are drawn at this alpha; masked boxes at 1.
export const DIM_ALPHA = 0.35;

// Over the base skin, empty boxes are veiled with this so masked boxes stand out.
export const EMPTY_VEIL = 'rgba(241, 243, 245, 0.62)';

// One box per (layer, face): the face rectangle inside the 64x64 atlas.
// `subFaces` lists faces that have a per-model (slim) grid; those boxes carry
// sub: 'slim' so reads and writes go to the slim override.
export function buildBoxes(rects, subFaces = null) {
  const subs = new Set(subFaces || []);
  const boxes = [];
  for (const layer of ['L1', 'L2']) {
    for (const [face, [x, y, w, h]] of Object.entries((rects && rects[layer]) || {})) {
      const box = { layer, face, x, y, w, h };
      if (subs.has(face)) box.sub = 'slim';
      boxes.push(box);
    }
  }
  return boxes;
}

export function boxAt(boxes, u, v) {
  return boxes.find((b) => u >= b.x && u < b.x + b.w && v >= b.y && v < b.y + b.h) || null;
}

export function gridHasMask(grid) {
  return !!grid && grid.some((row) => row.some(Boolean));
}

export function boxAlpha(hasMask) {
  return hasMask ? 1 : DIM_ALPHA;
}

// All texels on the line from (x0,y0) to (x1,y1), inclusive. Used so a fast
// mouse stroke leaves no gaps between pointer samples.
export function bresenham(x0, y0, x1, y1) {
  const pts = [];
  const dx = Math.abs(x1 - x0);
  const sx = x0 < x1 ? 1 : -1;
  const dy = -Math.abs(y1 - y0);
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  let x = x0;
  let y = y0;
  for (;;) {
    pts.push([x, y]);
    if (x === x1 && y === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x += sx; }
    if (e2 <= dx) { err += dx; y += sy; }
  }
  return pts;
}

// Screen pixel -> texel, or null when outside the atlas.
export function texelAt(clientX, clientY, rect, zoom) {
  const u = Math.floor((clientX - rect.left) / zoom);
  const v = Math.floor((clientY - rect.top) / zoom);
  if (u < 0 || v < 0 || u >= ATLAS || v >= ATLAS) return null;
  return { u, v };
}

// Draw the atlas. `cellOn(box, u, v)` and `hasMaskFor(box)` read the current
// mask; `opts.activeBox`, `opts.hover` and `opts.base` are optional.
export function drawAtlas(ctx, opts) {
  const { boxes, zoom, cellOn, hasMaskFor, activeBox, hover, base } = opts;
  const size = ATLAS * zoom;
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = '#f1f3f5';
  ctx.fillRect(0, 0, size, size);

  // 1. Background. With a base skin: the real output pixels, with empty boxes
  // veiled. Without: the palette, masked boxes bright and empty boxes dimmed.
  if (base) {
    ctx.drawImage(base, 0, 0, size, size);
    ctx.fillStyle = EMPTY_VEIL;
    for (const b of boxes) {
      if (!hasMaskFor(b)) ctx.fillRect(b.x * zoom, b.y * zoom, b.w * zoom, b.h * zoom);
    }
  } else {
    for (const b of boxes) {
      ctx.globalAlpha = boxAlpha(hasMaskFor(b));
      ctx.fillStyle = LAYER_STYLE[b.layer].base;
      ctx.fillRect(b.x * zoom, b.y * zoom, b.w * zoom, b.h * zoom);
    }
    ctx.globalAlpha = 1;
  }

  // 2. Masked texels: tint plus hatch in the layer's own direction/colour.
  const lineWidth = Math.max(1, zoom / 8);
  for (const b of boxes) {
    const style = LAYER_STYLE[b.layer];
    ctx.fillStyle = style.tint;
    ctx.strokeStyle = style.line;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    for (let v = 0; v < b.h; v++) {
      for (let u = 0; u < b.w; u++) {
        if (!cellOn(b, u, v)) continue;
        const x0 = (b.x + u) * zoom;
        const y0 = (b.y + v) * zoom;
        ctx.fillRect(x0, y0, zoom, zoom);
        if (style.hatch === 'backslash') {
          ctx.moveTo(x0, y0); ctx.lineTo(x0 + zoom, y0 + zoom);
        } else {
          ctx.moveTo(x0 + zoom, y0); ctx.lineTo(x0, y0 + zoom);
        }
      }
    }
    ctx.stroke();
  }

  // 3. Texel grid (only when zoomed in enough to be useful).
  if (zoom >= 6) {
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.10)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const b of boxes) {
      for (let u = 0; u <= b.w; u++) {
        const x = (b.x + u) * zoom + 0.5;
        ctx.moveTo(x, b.y * zoom); ctx.lineTo(x, (b.y + b.h) * zoom);
      }
      for (let v = 0; v <= b.h; v++) {
        const y = (b.y + v) * zoom + 0.5;
        ctx.moveTo(b.x * zoom, y); ctx.lineTo((b.x + b.w) * zoom, y);
      }
    }
    ctx.stroke();
  }

  // 4. Box outlines, then the active box on top.
  ctx.strokeStyle = 'rgba(15, 23, 42, 0.45)';
  ctx.lineWidth = 1;
  for (const b of boxes) ctx.strokeRect(b.x * zoom + 0.5, b.y * zoom + 0.5, b.w * zoom - 1, b.h * zoom - 1);
  if (activeBox) {
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 2;
    ctx.strokeRect(activeBox.x * zoom + 1, activeBox.y * zoom + 1, activeBox.w * zoom - 2, activeBox.h * zoom - 2);
  }

  // 5. Labels when zoomed in enough to read them.
  if (zoom >= 7) {
    ctx.fillStyle = '#111827';
    ctx.font = `${Math.min(11, Math.max(8, zoom))}px system-ui, sans-serif`;
    ctx.textBaseline = 'top';
    for (const b of boxes) {
      const label = b.face.split('.', 2)[1];
      ctx.fillText(label, b.x * zoom + 2, b.y * zoom + 2, Math.max(1, b.w * zoom - 4));
    }
  }

  // 6. Hover cursor.
  if (hover) {
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.strokeRect(hover.u * zoom + 1, hover.v * zoom + 1, zoom - 2, zoom - 2);
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 1;
    ctx.strokeRect(hover.u * zoom + 0.5, hover.v * zoom + 0.5, zoom - 1, zoom - 1);
  }
}
