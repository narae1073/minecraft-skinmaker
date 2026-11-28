import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ATTR_GROUPS, ATTR_FIELDS, ATTR_LABELS, attrText, hairWarning, HAT_DEFAULT } from './panel.js';

test('every editable attribute appears exactly once across the groups', () => {
  const seen = ATTR_GROUPS.flatMap((g) => g.fields);
  assert.equal(seen.length, new Set(seen).size, 'no duplicate fields');
  assert.deepEqual(seen, ATTR_FIELDS);
  assert.equal(ATTR_FIELDS.length, 14);
});

test('groups keep the user-facing body areas', () => {
  assert.deepEqual(ATTR_GROUPS.map((g) => g.title), ['상의', '하의', '머리', '액세서리', '얼굴']);
});

test('every field has a Korean label and text for its enum values', () => {
  for (const key of ATTR_FIELDS) {
    assert.ok(ATTR_LABELS[key], `label missing for ${key}`);
    assert.notEqual(attrText(key, 'definitely-not-a-value'), undefined);
  }
  // Shared enum names must not collide in the UI text.
  assert.equal(attrText('sleeve_len', 'short'), '반팔');
  assert.equal(attrText('hair_length', 'short'), '숏');
  assert.equal(attrText('hood_fit', 'shallow'), '얕게');
});

test('contradictory hair pairs warn, compatible pairs do not', () => {
  assert.ok(hairWarning('short', 'very_long'));
  assert.ok(hairWarning('long_straight', 'short'));
  assert.ok(hairWarning('bun', 'short'));  // tied-up bun is still a long style
  assert.equal(hairWarning('long_straight', 'long'), '');
  assert.equal(hairWarning('bob', 'medium'), '');
  assert.equal(hairWarning('bob', 'short'), '');
});

test('hat colours have a default per headwear value', () => {
  assert.equal(HAT_DEFAULT.cap, '#e9eef3');
  assert.equal(HAT_DEFAULT.beanie, '#1f1f1f');
});
