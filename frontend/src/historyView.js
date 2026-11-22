// Sidebar history labels. The TTL itself lives in skinHistory.js so the
// sanitiser and the UI never disagree about when an item expires.
import { HISTORY_TTL_MS } from './skinHistory';

const DAY_MS = 24 * 60 * 60 * 1000;
export const EXPIRING_SOON_DAYS = 2;

/** Days until the 14-day TTL drops the item (0 means it is gone). */
export function daysLeft(createdAt, now = Date.now()) {
  if (!Number.isFinite(createdAt)) return 0;
  const left = createdAt + HISTORY_TTL_MS - now;
  return Math.max(0, Math.ceil(left / DAY_MS));
}

/** Relative creation label: 오늘 / 어제 / n일 전. */
export function createdAtLabel(createdAt, now = Date.now()) {
  if (!Number.isFinite(createdAt)) return '';
  const days = Math.floor(Math.max(0, now - createdAt) / DAY_MS);
  if (days <= 0) return '오늘';
  if (days === 1) return '어제';
  return `${days}일 전`;
}

/** True when the item has EXPIRING_SOON_DAYS or fewer days left. */
export function isExpiringSoon(createdAt, now = Date.now()) {
  const left = daysLeft(createdAt, now);
  return left > 0 && left <= EXPIRING_SOON_DAYS;
}

/** Both labels the sidebar renders for one item. */
export function historyMeta(createdAt, now = Date.now()) {
  const left = daysLeft(createdAt, now);
  return {
    created: createdAtLabel(createdAt, now),
    left,
    expiry: left > 0 ? `${left}일 남음` : '만료됨',
    expiring: isExpiringSoon(createdAt, now),
  };
}
