/**
 * Pure builder for POST /copilot/suggest body (extension live assist).
 * Live help is meetings only — non-meeting callMode yields null (no fetch).
 */

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
    product_context: productContext,
    language: 'auto',
    call_mode: 'meeting',
    speaker_role:
      speakerRole === 'rep' || speakerRole === 'unknown' ? speakerRole : 'prospect',
  };

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
