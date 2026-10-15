/** The stored list of dismissed keys, as the next list after one change. Each change starts from what
 * is stored, not from a component's copy, so several instances sharing a scope never overwrite each other. */
export function parseDismissed(raw: string | null): Set<string> {
  try {
    const list = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(list) ? list.map(String) : []);
  } catch {
    return new Set();
  }
}

export function addDismissed(raw: string | null, key: string): Set<string> {
  return parseDismissed(raw).add(key);
}

export function removeDismissed(raw: string | null, key: string): Set<string> {
  const keys = parseDismissed(raw);
  keys.delete(key);
  return keys;
}
