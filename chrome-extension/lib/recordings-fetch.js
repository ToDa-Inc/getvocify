/**
 * When to fetch HubSpot recordings, and whether a response may land.
 *
 * Off a CRM record the scope is "inbox". That path skip-broadcasts, so a
 * poisoned cache (spinner on, nothing in flight) never retries unless this
 * planner says fetch.
 */

export function planRecordingsFetch({
  scopeKey,
  cacheKey = null,
  inFlightKey = null,
  loading = false,
  force = false,
} = {}) {
  if (force) return { action: 'fetch' };
  if (inFlightKey === scopeKey) return { action: 'skip' };
  if (loading && inFlightKey == null) return { action: 'fetch' };
  if (cacheKey === scopeKey) return { action: 'skip' };
  return { action: 'fetch' };
}

export function planRecordingsResult({
  gen,
  fetchGen,
  resultScopeKey,
  currentScopeKey,
} = {}) {
  if (gen !== fetchGen) return { action: 'ignore' };
  if (resultScopeKey !== currentScopeKey) return { action: 'abandon' };
  return { action: 'apply' };
}
