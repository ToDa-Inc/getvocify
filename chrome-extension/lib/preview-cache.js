/**
 * In-flight + short-lived HubSpot preview cache.
 * Lets processing-poll prefetch complete before Review & sync paints.
 */

const TTL_MS = 5 * 60 * 1000;
const cache = new Map();
const inflight = new Map();

export function previewCacheKey({
  memoId = null,
  dealId = null,
  contactId = null,
  createNewDeal = false,
} = {}) {
  return [
    String(memoId || ''),
    String(dealId || ''),
    String(contactId || ''),
    createNewDeal ? '1' : '0',
  ].join('|');
}

export function getCachedPreview(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.cachedAt > TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.preview;
}

export function setCachedPreview(key, preview) {
  if (!key || !preview || preview.error) return;
  cache.set(key, { preview, cachedAt: Date.now() });
}

export function getInflightPreview(key) {
  return inflight.get(key) || null;
}

export function setInflightPreview(key, promise) {
  if (!key || !promise) return;
  inflight.set(key, promise);
}

export function clearInflightPreview(key) {
  inflight.delete(key);
}

export function clearPreviewCache(memoId = null) {
  if (memoId == null) {
    cache.clear();
    inflight.clear();
    return;
  }
  const prefix = `${String(memoId)}|`;
  for (const key of [...cache.keys()]) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
  for (const key of [...inflight.keys()]) {
    if (key.startsWith(prefix)) inflight.delete(key);
  }
}
