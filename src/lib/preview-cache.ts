const TTL_MS = 5 * 60 * 1000;

type PreviewCacheEntry = {
  preview: unknown;
  cachedAt: number;
  cacheKey: string;
};

const cache = new Map<string, PreviewCacheEntry>();

export function previewCacheKey(initialDealId?: string | null): string {
  return initialDealId || "default";
}

export function getCachedPreview(memoId: string, cacheKey: string): unknown | null {
  const entry = cache.get(memoId);
  if (!entry || entry.cacheKey !== cacheKey) return null;
  if (Date.now() - entry.cachedAt > TTL_MS) {
    cache.delete(memoId);
    return null;
  }
  return entry.preview;
}

export function setCachedPreview(memoId: string, cacheKey: string, preview: unknown): void {
  cache.set(memoId, { preview, cachedAt: Date.now(), cacheKey });
}

export function clearCachedPreview(memoId: string): void {
  cache.delete(memoId);
}
