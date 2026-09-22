/** Keep in sync with LEGACY_DEFAULT_PRODUCT_CONTEXT in src/features/copilot/types.ts */
export const LEGACY_DEFAULT_PRODUCT_CONTEXT = `Product: Vocify — AI voice memos that extract CRM fields and sync to HubSpot after sales calls.
Ideal customer: B2B sales teams / founders who hate typing notes into CRM after calls.
Pain: Lost deal context, delayed CRM hygiene, reps avoid logging calls.
Value: Speak after (or during) the call → structured fields → push to CRM in seconds.
Proof angles: Speeds CRM updates, reduces forgotten follow-ups, keeps pipeline trustworthy.
Tone: Direct, founder-to-founder, no fluff. Spanish or English OK.`;

export const PRODUCT_CONTEXT_STORAGE_KEY = 'vocify_copilot_product_context';

const LEGACY_DEFAULT_PRODUCT_CONTEXT_TRIMMED =
  LEGACY_DEFAULT_PRODUCT_CONTEXT.trim();

/** Local storage value: blank or legacy pitch counts as empty. */
export function normalizeStoredProductContext(value) {
  const trimmed = String(value ?? '').trim();
  if (!trimmed || trimmed === LEGACY_DEFAULT_PRODUCT_CONTEXT_TRIMMED) {
    return '';
  }
  return trimmed;
}

/**
 * Pure resolution for live suggest: local custom text wins; else profile; else omit (empty string).
 * Does not fetch — callers pass profileProductContext when known.
 */
export function resolveProductContextForSuggest(localProductContext, profileProductContext) {
  const local = normalizeStoredProductContext(localProductContext);
  if (local) return local;
  const profile = String(profileProductContext ?? '').trim();
  if (profile) return profile;
  return '';
}
