/**
 * HubSpot hs_call_duration is milliseconds.
 * Prefer duration_ms from the API. Fall back for older payloads that sent
 * unconverted ms as duration_seconds (5000 → 83 minutes).
 */

export function callDurationSeconds(rec) {
  if (!rec || typeof rec !== 'object') return 0;
  if (rec.duration_ms != null && rec.duration_ms !== '') {
    const ms = Number(rec.duration_ms);
    if (Number.isFinite(ms) && ms > 0) return ms / 1000;
  }
  const n = Number(rec.duration_seconds);
  if (!Number.isFinite(n) || n <= 0) return 0;
  if (n > 1000 && n <= 10000) return n / 1000;
  return n;
}

export function formatCallDuration(seconds) {
  const total = Math.round(Number(seconds));
  if (!total || total <= 0) return '';
  const m = Math.floor(total / 60);
  const r = total % 60;
  if (m <= 0) return `${r}s`;
  return r ? `${m}m ${r}s` : `${m}m`;
}
