/**
 * Scope keys for HubSpot page context. Cache is valid only for the same
 * objectType + recordId. A different deal/contact must not keep the old name,
 * recordings, or memos.
 */

export function recordScopeKey(ctx) {
  if (!ctx?.objectType || ctx.recordId == null || ctx.recordId === '') return null;
  return `${ctx.objectType}:${ctx.recordId}`;
}

/** Recordings cache: a HubSpot record, or the portal inbox. */
export function recordingsScopeKey(ctx) {
  return recordScopeKey(ctx) || 'inbox';
}

const KEEP_IF_MISSING = [
  'dealName',
  'contactName',
  'companyName',
  'contactEmail',
  'contactPhone',
  'contactId',
  'companyId',
  'dealContacts',
  'companyContacts',
  '_enrichedKey',
];

/**
 * Same CRM record → keep enriched names. Different record → use the new
 * URL context only (no leftover deal/contact title).
 */
export function mergePageContext(prev, next) {
  if (!next) {
    return { sameRecord: false, context: null };
  }
  const prevKey = recordScopeKey(prev);
  const nextKey = recordScopeKey(next);
  if (!nextKey || prevKey !== nextKey) {
    return { sameRecord: false, context: next };
  }
  const merged = { ...prev, ...next };
  for (const field of KEEP_IF_MISSING) {
    if (merged[field] == null && prev?.[field] != null) {
      merged[field] = prev[field];
    }
  }
  return { sameRecord: true, context: merged };
}

/**
 * Same CRM record → keep the current panel. Any other page (including closing
 * the deal) must drop names/lists immediately — do not reuse inbox/deal cache
 * as an excuse to skip the broadcast.
 */
/**
 * Review session: never replace the process's page with a later focused record.
 * Same record may pick up names/associations. Inbox stays inbox.
 */
export function keepReviewSessionContext(locked, next) {
  if (!locked) return next || {};
  const lockedKey = recordScopeKey(locked);
  const nextKey = recordScopeKey(next);
  if (lockedKey !== nextKey) return locked;
  return { ...locked, ...(next || {}) };
}

export function planPageContextUpdate(prev, next) {
  const { context, sameRecord } = mergePageContext(prev, next);
  const prevScope = recordingsScopeKey(prev);
  const nextScope = recordingsScopeKey(context);
  const sameScope = prevScope === nextScope;
  return {
    context,
    sameRecord,
    skipBroadcast: sameRecord || (sameScope && !recordScopeKey(prev) && !recordScopeKey(context)),
    replaceLists: !sameScope,
  };
}

const IDENTITY_FIELDS = [
  'dealName',
  'contactName',
  'companyName',
  'contactEmail',
  'contactPhone',
  'contactId',
  'companyId',
  'dealContacts',
  'companyContacts',
];

const IDENTITY_CACHE_MAX = 40;

function identitySnapshot(ctx) {
  const key = recordScopeKey(ctx);
  if (!key) return null;
  const snap = { objectType: ctx.objectType, recordId: ctx.recordId };
  let useful = false;
  for (const field of IDENTITY_FIELDS) {
    if (ctx[field] != null) {
      snap[field] = ctx[field];
      useful = true;
    }
  }
  return useful ? snap : null;
}

/** Paint name/phone from a prior visit to this exact record. Never copies another record. */
export function hydrateFromIdentityCache(urlCtx, cache) {
  const key = recordScopeKey(urlCtx);
  if (!key || !cache) return urlCtx;
  const cached = cache instanceof Map ? cache.get(key) : cache[key];
  if (!cached) return urlCtx;
  const next = { ...urlCtx };
  for (const field of IDENTITY_FIELDS) {
    if (cached[field] != null) next[field] = cached[field];
  }
  return next;
}

export function rememberIdentity(cache, enriched, maxEntries = IDENTITY_CACHE_MAX) {
  const key = recordScopeKey(enriched);
  const snap = identitySnapshot(enriched);
  const next = cache instanceof Map ? new Map(cache) : new Map();
  if (!key || !snap) return next;
  if (next.has(key)) next.delete(key);
  next.set(key, snap);
  while (next.size > maxEntries) {
    next.delete(next.keys().next().value);
  }
  return next;
}

export function identityCacheToEntries(cache) {
  return cache instanceof Map ? [...cache.entries()] : [];
}

export function identityCacheFromEntries(entries) {
  return new Map(Array.isArray(entries) ? entries : []);
}
