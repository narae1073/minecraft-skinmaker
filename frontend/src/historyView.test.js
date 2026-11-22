import { describe, expect, it } from 'vitest';
import { HISTORY_TTL_MS } from './skinHistory';
import {
  EXPIRING_SOON_DAYS,
  createdAtLabel,
  daysLeft,
  historyMeta,
  isExpiringSoon,
} from './historyView';

const NOW = Date.now();
const DAY = 24 * 60 * 60 * 1000;

describe('daysLeft', () => {
  it('counts down from 14 days and rounds partial days up', () => {
    expect(daysLeft(NOW, NOW)).toBe(14);
    expect(daysLeft(NOW - DAY, NOW)).toBe(13);
    expect(daysLeft(NOW - 13 * DAY, NOW)).toBe(1);
    expect(daysLeft(NOW - 13 * DAY - 1, NOW)).toBe(1);
    expect(daysLeft(NOW - 13 * DAY - DAY / 2, NOW)).toBe(1);
    expect(daysLeft(NOW - HISTORY_TTL_MS, NOW)).toBe(0);
  });

  it('clamps at zero instead of going negative', () => {
    expect(daysLeft(NOW - HISTORY_TTL_MS - 5 * DAY, NOW)).toBe(0);
    expect(daysLeft(Number.NaN, NOW)).toBe(0);
  });
});

describe('createdAtLabel', () => {
  it('labels today, yesterday and older items', () => {
    expect(createdAtLabel(NOW, NOW)).toBe('오늘');
    expect(createdAtLabel(NOW - 3 * 60 * 60 * 1000, NOW)).toBe('오늘');
    expect(createdAtLabel(NOW - DAY, NOW)).toBe('어제');
    expect(createdAtLabel(NOW - 2 * DAY, NOW)).toBe('2일 전');
    expect(createdAtLabel(NOW - 13 * DAY, NOW)).toBe('13일 전');
  });

  it('treats future timestamps inside the clock-skew window as today', () => {
    expect(createdAtLabel(NOW + 60 * 1000, NOW)).toBe('오늘');
    expect(createdAtLabel(undefined, NOW)).toBe('');
  });
});

describe('isExpiringSoon', () => {
  it('flags the last EXPIRING_SOON_DAYS days only', () => {
    expect(EXPIRING_SOON_DAYS).toBe(2);
    expect(isExpiringSoon(NOW, NOW)).toBe(false);
    expect(isExpiringSoon(NOW - 11 * DAY, NOW)).toBe(false); // 3일 남음
    expect(isExpiringSoon(NOW - 12 * DAY, NOW)).toBe(true); // 2일 남음
    expect(isExpiringSoon(NOW - 13 * DAY, NOW)).toBe(true);
    expect(isExpiringSoon(NOW - HISTORY_TTL_MS, NOW)).toBe(false);
  });
});

describe('historyMeta', () => {
  it('returns labels for a fresh item', () => {
    expect(historyMeta(NOW, NOW)).toEqual({
      created: '오늘',
      left: 14,
      expiry: '14일 남음',
      expiring: false,
    });
  });

  it('returns the warning flag for an item in its final days', () => {
    const meta = historyMeta(NOW - 12 * DAY, NOW);
    expect(meta.left).toBe(2);
    expect(meta.expiry).toBe('2일 남음');
    expect(meta.expiring).toBe(true);
  });

  it('marks expired items as 만료됨 without the warning flag', () => {
    expect(historyMeta(NOW - HISTORY_TTL_MS - 1, NOW)).toEqual({
      created: '14일 전',
      left: 0,
      expiry: '만료됨',
      expiring: false,
    });
  });
});
