import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickValue, rememberValue, resolveMaskTarget } from './selection.js';

const HAIR_STYLE = ['short', 'pixie', 'bob', 'long_straight', 'long_wavy', 'curly', 'ponytail', 'bun'];
const HAIR_LENGTH = ['short', 'medium', 'long', 'very_long'];

test('a value shared by the new key is kept', () => {
  // hair_style.short -> hair_length keeps `short` instead of resetting.
  assert.equal(pickValue(HAIR_LENGTH, { current: 'short', key: 'hair_length', lastValue: {} }), 'short');
  assert.equal(pickValue(HAIR_STYLE, { current: 'short', key: 'hair_style', lastValue: {} }), 'short');
});

test('a previously chosen value is restored when the key has no such value', () => {
  const last = {};
  rememberValue(last, 'hair_style', 'curly');
  assert.equal(pickValue(HAIR_LENGTH, { current: 'curly', key: 'hair_length', lastValue: last }), 'short');
  rememberValue(last, 'hair_length', 'very_long');
  assert.equal(pickValue(HAIR_LENGTH, { current: 'curly', key: 'hair_length', lastValue: last }), 'very_long');
  assert.equal(pickValue(HAIR_STYLE, { current: 'very_long', key: 'hair_style', lastValue: last }), 'curly');
});

test('falls back to the first value for an unknown key or empty memory', () => {
  assert.equal(pickValue(HAIR_LENGTH, { current: 'curly', key: 'hood', lastValue: {} }), 'short');
  assert.equal(pickValue(['shallow'], { current: 'normal', key: 'hood_fit', lastValue: {} }), 'shallow');
  assert.equal(pickValue([], { current: 'x' }), null);
});

test('rememberValue stores per key without disturbing other keys', () => {
  const last = {};
  rememberValue(last, 'hair_style', 'bob');
  rememberValue(last, 'hair_length', 'long');
  rememberValue(last, 'hair_style', 'bun');
  assert.deepEqual(last, { hair_style: 'bun', hair_length: 'long' });
});

test('resolveMaskTarget reports a fallback instead of silently switching', () => {
  assert.deepEqual(resolveMaskTarget(HAIR_STYLE, 'curly'), { value: 'curly', fallback: false });
  assert.deepEqual(resolveMaskTarget(['shallow'], 'normal'), { value: 'shallow', fallback: true });
  assert.deepEqual(resolveMaskTarget([], 'x'), { value: null, fallback: false });
});
