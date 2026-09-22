/**
 * Pure builder for POST /copilot/suggest body (extension live assist).
 * Live help is meetings only — non-meeting callMode yields null (no fetch).
 */

/** Keep in sync with LEGACY_DEFAULT_PRODUCT_CONTEXT in src/features/copilot/types.ts */
export const LEGACY_DEFAULT_PRODUCT_CONTEXT = `Product: Vocify — AI voice memos that extract CRM fields and sync to HubSpot after sales calls.
Ideal customer: B2B sales teams / founders who hate typing notes into CRM after calls.
Pain: Lost deal context, delayed CRM hygiene, reps avoid logging calls.
Value: Speak after (or during) the call → structured fields → push to CRM in seconds.
Proof angles: Speeds CRM updates, reduces forgotten follow-ups, keeps pipeline trustworthy.
Tone: Direct, founder-to-founder, no fluff. Spanish or English OK.`;

const LEGACY_DEFAULT_PRODUCT_CONTEXT_TRIMMED =
  LEGACY_DEFAULT_PRODUCT_CONTEXT.trim();

export function effectiveProductContext(raw) {
  const trimmed = String(raw ?? '').trim();
  if (!trimmed || trimmed === LEGACY_DEFAULT_PRODUCT_CONTEXT_TRIMMED) {
    return '';
  }
  return trimmed;
}

export function shouldRunCopilotSuggest({ assistEnabled, callMode } = {}) {
  if (assistEnabled === false) return false;
  return callMode === 'meeting';
}

export function buildCopilotSuggestRequestBody({
  callMode,
  context = null,
  latestTurn,
  transcriptWindow,
  speakerRole = 'prospect',
  productContext,
} = {}) {
  if (callMode !== 'meeting') return null;

  const body = {
    transcript_window: String(transcriptWindow || '').slice(-6000),
    latest_turn: latestTurn,
    language: 'auto',
    call_mode: 'meeting',
    speaker_role:
      speakerRole === 'rep' || speakerRole === 'unknown' ? speakerRole : 'prospect',
  };

  const trimmedProductContext = effectiveProductContext(productContext);
  if (trimmedProductContext) {
    body.product_context = trimmedProductContext;
  }

  const recordId = context?.recordId;
  if (
    context?.objectType === 'contact' &&
    recordId != null &&
    String(recordId).trim() !== ''
  ) {
    body.contact_id = String(recordId);
  }

  return body;
}
