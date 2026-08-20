/**
 * In-flight + short-lived HubSpot preview cache.
 * Same identity as the extension: memo + deal + contact + create-new-deal.
 * A different call or CRM target must not reuse the previous preview.
 */

const TTL_MS = 5 * 60 * 1000;

type PreviewCacheEntry = {
  preview: unknown;
  cachedAt: number;
};

const cache = new Map<string, PreviewCacheEntry>();

export function previewCacheKey({
  memoId = "",
  dealId = null,
  contactId = null,
  createNewDeal = false,
  refreshKey = "",
}: {
  memoId?: string | null;
  dealId?: string | null;
  contactId?: string | null;
  createNewDeal?: boolean;
  refreshKey?: string | null;
} = {}): string {
  return [
    String(memoId || ""),
    String(dealId || ""),
    String(contactId || ""),
    createNewDeal ? "1" : "0",
    String(refreshKey || ""),
  ].join("|");
}

export function getCachedPreview(key: string): unknown | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.cachedAt > TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.preview;
}

export function setCachedPreview(key: string, preview: unknown): void {
  if (!key || preview == null || typeof preview !== "object") return;
  if ("error" in preview && (preview as { error?: unknown }).error) return;
  cache.set(key, { preview, cachedAt: Date.now() });
}

export function clearCachedPreview(memoId?: string | null): void {
  if (memoId == null || memoId === "") {
    cache.clear();
    return;
  }
  const prefix = `${String(memoId)}|`;
  for (const key of [...cache.keys()]) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}
