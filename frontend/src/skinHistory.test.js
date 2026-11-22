import { describe, expect, it, vi } from 'vitest';
import {
  HISTORY_MAX,
  HISTORY_STORAGE_KEY,
  HISTORY_TTL_MS,
  loadSkinHistory,
  sanitizeHistory,
  sanitizeHistoryItem,
  saveSkinHistory,
} from './skinHistory';

const NOW = Date.now();
const SKIN = '/static/skins/abcdef123456_c1.png';
const FLAT = '/static/skins/abcdef123456_c1_flat.png';
const STEPS = {
  clean: '/static/steps/abcdef123456_clean.png',
  full: '/static/steps/abcdef123456_full.png',
};

function item(overrides = {}) {
  return {
    url: SKIN,
    flatUrl: FLAT,
    varied: 'hair tone',
    steps: STEPS,
    model: 'slim',
    jobId: 'abcdef123456',
    createdAt: NOW - 1000,
    ...overrides,
  };
}

function memoryStorage(seed) {
  const data = new Map();
  if (seed !== undefined) data.set(HISTORY_STORAGE_KEY, seed);
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, value),
    dump: () => data.get(HISTORY_STORAGE_KEY),
  };
}

describe('sanitizeHistoryItem', () => {
  it('keeps a valid item and normalises the optional fields', () => {
    expect(sanitizeHistoryItem(item(), NOW)).toEqual({
      url: SKIN,
      flatUrl: FLAT,
      varied: 'hair tone',
      steps: STEPS,
      model: 'slim',
      jobId: 'abcdef123456',
      createdAt: NOW - 1000,
    });
  });

  it('drops anything without a /static/skins PNG url', () => {
    for (const url of [
      undefined,
      '',
      'https://evil.example/skin.png',
      '/static/skins/../../etc/passwd',
      '/static/steps/abcdef123456_clean.png',
      'javascript:alert(1)',
    ]) {
      expect(sanitizeHistoryItem(item({ url }), NOW)).toBeNull();
    }
  });

  it('rejects items with no timestamp, future timestamps, or an expired TTL', () => {
    expect(sanitizeHistoryItem(item({ createdAt: undefined }), NOW)).toBeNull();
    expect(sanitizeHistoryItem(item({ createdAt: 'yesterday' }), NOW)).toBeNull();
    expect(sanitizeHistoryItem(item({ createdAt: 0 }), NOW)).toBeNull();
    // Small clock skew is tolerated, a big jump is not.
    expect(sanitizeHistoryItem(item({ createdAt: NOW + 60_000 }), NOW)).not.toBeNull();
    expect(sanitizeHistoryItem(item({ createdAt: NOW + 10 * 60_000 }), NOW)).toBeNull();
  });

  it('keeps the TTL boundary inclusive and drops one millisecond past it', () => {
    expect(sanitizeHistoryItem(item({ createdAt: NOW - HISTORY_TTL_MS }), NOW)).not.toBeNull();
    expect(sanitizeHistoryItem(item({ createdAt: NOW - HISTORY_TTL_MS - 1 }), NOW)).toBeNull();
  });

  it('clears optional fields that fail their own validation', () => {
    const clean = sanitizeHistoryItem(
      item({ flatUrl: '/static/steps/x.png', steps: { clean: STEPS.clean }, model: 'wide', jobId: '../../etc' }),
      NOW,
    );
    expect(clean.flatUrl).toBeNull();
    expect(clean.steps).toBeNull();
    expect(clean.model).toBe('classic');
    expect(clean.jobId).toBeNull();
    expect(clean.varied).toBe('hair tone');
  });

  it('truncates long free-text and ignores non-string values', () => {
    expect(sanitizeHistoryItem(item({ varied: 'x'.repeat(500) }), NOW).varied).toHaveLength(200);
    expect(sanitizeHistoryItem(item({ varied: 42 }), NOW).varied).toBe('');
    expect(sanitizeHistoryItem(null, NOW)).toBeNull();
    expect(sanitizeHistoryItem('not an item', NOW)).toBeNull();
  });
});

describe('sanitizeHistory', () => {
  it('returns [] for non-arrays', () => {
    expect(sanitizeHistory(undefined, NOW)).toEqual([]);
    expect(sanitizeHistory({ url: SKIN }, NOW)).toEqual([]);
  });

  it('drops invalid rows and keeps the newest HISTORY_MAX items', () => {
    const rows = [
      { url: 'bad' },
      ...Array.from({ length: HISTORY_MAX + 5 }, (_, i) =>
        item({ url: `/static/skins/skin_${i}.png`, createdAt: NOW - 1000 - i }),
      ),
    ];
    const clean = sanitizeHistory(rows, NOW);
    expect(clean).toHaveLength(HISTORY_MAX);
    expect(clean[0].url).toBe('/static/skins/skin_5.png');
    expect(clean.at(-1).url).toBe(`/static/skins/skin_${HISTORY_MAX + 4}.png`);
  });
});

describe('loadSkinHistory / saveSkinHistory', () => {
  it('round-trips through storage', () => {
    const storage = memoryStorage();
    saveSkinHistory([item()], storage);
    const loaded = loadSkinHistory(storage);
    expect(loaded).toHaveLength(1);
    expect(loaded[0]).toEqual(sanitizeHistoryItem(item()));
  });

  it('returns [] for missing, malformed, or hostile storage contents', () => {
    expect(loadSkinHistory(memoryStorage())).toEqual([]);
    expect(loadSkinHistory(memoryStorage('{not json'))).toEqual([]);
    expect(loadSkinHistory(memoryStorage('"a string"'))).toEqual([]);
    expect(loadSkinHistory(memoryStorage('{"url":"/static/skins/a.png"}'))).toEqual([]);
  });

  it('never throws when storage is unavailable or full', () => {
    const throwing = {
      getItem: vi.fn(() => {
        throw new Error('blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('quota');
      }),
    };
    expect(loadSkinHistory(throwing)).toEqual([]);
    expect(() => saveSkinHistory([item()], throwing)).not.toThrow();
    expect(() => loadSkinHistory(throwing)).not.toThrow();
  });

  it('writes sanitised rows and caps the list', () => {
    const storage = memoryStorage();
    const rows = [
      { url: 'bad' },
      ...Array.from({ length: HISTORY_MAX + 3 }, (_, i) => item({ url: `/static/skins/skin_${i}.png` })),
    ];
    saveSkinHistory(rows, storage);
    const written = JSON.parse(storage.dump());
    expect(written).toHaveLength(HISTORY_MAX);
    expect(written.every((row) => row.url.startsWith('/static/skins/skin_'))).toBe(true);
  });
});
