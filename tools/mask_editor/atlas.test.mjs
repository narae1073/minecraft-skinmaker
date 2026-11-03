import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildBoxes, boxAt, gridHasMask, boxAlpha, bresenham, DIM_ALPHA, texelAt } from './atlas.js';

const rects = {
  L1: { 'head.front': [8, 8, 8, 8], 'body.front': [20, 20, 8, 12] },
  L2: { 'head.front': [40, 8, 8, 8] },
};

test('buildBoxes emits one box per face per layer', () => {
  const boxes = buildBoxes(rects);
  assert.equal(boxes.length, 3);
  assert.deepEqual(boxes[0], { layer: 'L1', face: 'head.front', x: 8, y: 8, w: 8, h: 8 });
  assert.equal(boxes[2].layer, 'L2');
});

test('boxAt finds the containing box or null', () => {
  const boxes = buildBoxes(rects);
  assert.equal(boxAt(boxes, 8, 8).face, 'head.front');
  assert.equal(boxAt(boxes, 15, 15).face, 'head.front');
  assert.equal(boxAt(boxes, 16, 15), null);
  assert.equal(boxAt(boxes, 40, 8).layer, 'L2');
  assert.equal(boxAt(boxes, 0, 0), null);
});

test('gridHasMask and dim/brighten rule', () => {
  assert.equal(gridHasMask([[0, 0], [0, 0]]), false);
  assert.equal(gridHasMask([[0, 0], [0, 1]]), true);
  assert.equal(gridHasMask(null), false);
  assert.equal(boxAlpha(true), 1);
  assert.equal(boxAlpha(false), DIM_ALPHA);
  assert.ok(DIM_ALPHA < 1);
});

test('bresenham covers every texel of a diagonal and straight stroke without gaps', () => {
  const diag = bresenham(0, 0, 4, 4);
  assert.deepEqual(diag, [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]);
  const line = bresenham(2, 5, 6, 5);
  assert.deepEqual(line, [[2, 5], [3, 5], [4, 5], [5, 5], [6, 5]]);
  // every step moves at most one texel in each axis: no gaps
  const path = bresenham(0, 0, 9, 3);
  for (let i = 1; i < path.length; i++) {
    assert.ok(Math.abs(path[i][0] - path[i - 1][0]) <= 1 && Math.abs(path[i][1] - path[i - 1][1]) <= 1);
  }
  assert.deepEqual(path[path.length - 1], [9, 3]);
  assert.deepEqual(bresenham(3, 3, 3, 3), [[3, 3]]);
});

test('bresenham handles reversed direction', () => {
  assert.deepEqual(bresenham(4, 0, 0, 0), [[4, 0], [3, 0], [2, 0], [1, 0], [0, 0]]);
});

test('texelAt maps client pixels to texels and rejects outside', () => {
  const rect = { left: 100, top: 50 };
  assert.deepEqual(texelAt(100, 50, rect, 8), { u: 0, v: 0 });
  assert.deepEqual(texelAt(117, 58, rect, 8), { u: 2, v: 1 });
  assert.equal(texelAt(99, 50, rect, 8), null);
  assert.equal(texelAt(100 + 64 * 8, 50, rect, 8), null);
});

test('buildBoxes marks slim sub-faces so they read and write the slim grid', () => {
  const boxes = buildBoxes({ L1: { 'r_arm.front': [40, 20, 3, 12], 'r_arm.right': [48, 20, 4, 12] }, L2: {} }, ['r_arm.front']);
  assert.equal(boxes.find((b) => b.face === 'r_arm.front').sub, 'slim');
  assert.equal(boxes.find((b) => b.face === 'r_arm.right').sub, undefined);
  assert.equal(buildBoxes(rects)[0].sub, undefined);
});
