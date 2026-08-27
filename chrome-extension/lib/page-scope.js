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
