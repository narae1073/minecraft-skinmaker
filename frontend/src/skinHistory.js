/**
 * Per-browser skin history.
 *
 * The list is a convenience cache, not authoritative state: every entry points
 * at a server file that is deleted after the retention window. Keep only
 * well-formed entries, drop anything older than the 14-day media retention,
 * and cap the list so localStorage cannot grow without bound.
 */
export const HISTORY_STORAGE_KEY = 'skinmaker.history.v1';
export const HISTORY_TTL_MS = 14 * 24 * 60 * 60 * 1000;
export const HISTORY_MAX = 100;

const SKIN_URL = /^\/static\/skins\/[A-Za-z0-9._-]+\.png$/;
const STEP_URL = /^\/static\/steps\/[A-Za-z0-9._-]+\.png$/;
const JOB_ID = /^[0-9a-f]{12}$/;
const CLOCK_SKEW_MS = 5 * 60 * 1000;

function safeString(value, max = 200) {
  return typeof value === 'string' ? value.slice(0, max) : '';
}

function sanitizeSteps(steps) {
  if (!steps || typeof steps !== 'object') return null;
  const clean = typeof steps.clean === 'string' && STEP_URL.test(steps.clean) ? steps.clean : null;
  const full = typeof steps.full === 'string' && STEP_URL.test(steps.full) ? steps.full : null;
  return clean && full ? { clean, full } : null;
}

export function sanitizeHistoryItem(item, now = Date.now()) {
  if (!item || typeof item !== 'object') return null;
  const url = typeof item.url === 'string' && SKIN_URL.test(item.url) ? item.url : null;
  if (!url) return null;

  const createdAt = Number.isFinite(item.createdAt) ? item.createdAt : 0;
  if (!createdAt || createdAt > now + CLOCK_SKEW_MS || now - createdAt > HISTORY_TTL_MS) {
    return null;
  }

  const flatUrl = typeof item.flatUrl === 'string' && SKIN_URL.test(item.flatUrl)
    ? item.flatUrl
    : null;
  const jobId = typeof item.jobId === 'string' && JOB_ID.test(item.jobId) ? item.jobId : null;

  return {
    url,
    flatUrl,
    varied: safeString(item.varied),
    steps: sanitizeSteps(item.steps),
    model: item.model === 'slim' ? 'slim' : 'classic',
    jobId,
    createdAt,
  };
}

export function sanitizeHistory(items, now = Date.now()) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => sanitizeHistoryItem(item, now))
    .filter(Boolean)
    .slice(-HISTORY_MAX);
}

export function loadSkinHistory(storage) {
  try {
    const store = storage || globalThis.localStorage;
    const raw = store?.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    return sanitizeHistory(JSON.parse(raw));
  } catch {
    return [];
  }
}

export function saveSkinHistory(items, storage) {
  try {
    const store = storage || globalThis.localStorage;
    store?.setItem(HISTORY_STORAGE_KEY, JSON.stringify(sanitizeHistory(items)));
  } catch {
    // Storage can be unavailable (private mode) or full; keep the in-memory list.
  }
}
