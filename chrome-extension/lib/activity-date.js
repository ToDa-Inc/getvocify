/**
 * Display timestamps for activity rows (HubSpot calls + Vocify memos).
 */

export function parseActivityTimestamp(value) {
  if (value == null || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** e.g. "Aug 19, 2026 · 3:35 PM" */
export function formatActivityTimestamp(value) {
  const d = parseActivityTimestamp(value);
  if (!d) return '';
  const datePart = d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const timePart = d.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
  return `${datePart} · ${timePart}`;
}

export function activityTimestampFromRecording(rec) {
  if (!rec) return null;
  return rec.timestamp || rec.timestamp_ms || rec.timestampMs || null;
}

export function activityTimestampFromMemo(memo) {
  if (!memo) return null;
  return memo.createdAt || memo.created_at || null;
}
