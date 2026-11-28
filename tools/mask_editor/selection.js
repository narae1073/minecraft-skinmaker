// Value picker for the mask-editor key/value tabs.
//
// Switching the mask key used to always jump back to the key's first value,
// which made it painful to work on hair_style / hair_length pairs. The rules
// below keep what the user was doing:
//
// 1. a value shared by the new key (e.g. `short`) is kept as-is,
// 2. otherwise the value last chosen for that key is restored,
// 3. otherwise the key's first value is used.
//
// `lastValue` maps key -> value and is updated whenever a value is chosen.

export function rememberValue(lastValue, key, value) {
  lastValue[key] = value;
  return lastValue;
}

export function pickValue(values, { current = null, key = null, lastValue = {} } = {}) {
  const list = Array.isArray(values) ? values : [];
  if (!list.length) return null;
  if (current !== null && list.includes(current)) return current;
  const remembered = key !== null ? lastValue[key] : null;
  if (remembered !== null && remembered !== undefined && list.includes(remembered)) return remembered;
  return list[0];
}

// Target resolution for the per-attribute "마스크" button: the requested value
// when this key can mask it, else the first maskable value plus a notice.
export function resolveMaskTarget(values, preferred) {
  const list = Array.isArray(values) ? values : [];
  if (!list.length) return { value: null, fallback: false };
  if (list.includes(preferred)) return { value: preferred, fallback: false };
  return { value: list[0], fallback: true };
}
