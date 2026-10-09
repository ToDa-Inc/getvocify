/**
 * Pure builder for POST /copilot/suggest body (extension live assist).
 * Live help is meetings only — non-meeting callMode yields null (no fetch).
 */

import {
  LEGACY_DEFAULT_PRODUCT_CONTEXT,
  normalizeStoredProductContext,
  resolveProductContextForSuggest,
} from '../shared/ui/copilot/product-context.js';

export { LEGACY_DEFAULT_PRODUCT_CONTEXT };

export function effectiveProductContext(raw) {
  return normalizeStoredProductContext(raw);
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
  profileProductContext,
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

  const resolved = resolveProductContextForSuggest(productContext, profileProductContext);
  if (resolved) {
    body.product_context = resolved;
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
