export const CONFIDENT_MATCH_THRESHOLD = 0.7;
export const PROCESSING_STATUSES = new Set([
  'uploading',
  'transcribing',
  'extracting',
  'pending_transcript',
]);

export function memoStatus(memo) {
  return String(memo?.status || '').trim();
}

export function isProcessingStatus(status) {
  return PROCESSING_STATUSES.has(status);
}

export function isReviewReady(status) {
  return status === 'pending_review';
}

export function pickDeal(matches, threshold = CONFIDENT_MATCH_THRESHOLD) {
  const list = Array.isArray(matches) ? matches.slice() : [];
  list.sort((a, b) => Number(b.match_confidence || 0) - Number(a.match_confidence || 0));
  const best = list[0] || null;
  if (best && Number(best.match_confidence || 0) >= threshold) {
    return { dealId: best.deal_id, needsDecision: false, selected: best };
  }
  return { dealId: null, needsDecision: list.length > 0, selected: null, matches: list };
}

export function approvePayload({
  dealId,
  isNewDeal = false,
  extraction,
  contactId,
  companyId,
  skipDeal = false,
} = {}) {
  return {
    deal_id: dealId || undefined,
    is_new_deal: Boolean(isNewDeal),
    extraction: extraction || undefined,
    contact_id: contactId || undefined,
    company_id: companyId || undefined,
    skip_deal: Boolean(skipDeal),
  };
}

export function notesFromPreview(preview, extraction) {
  const summary = String(
    extraction?.summary ||
      preview?.transcript_summary ||
      extraction?.raw_extraction?.description ||
      '',
  ).trim();
  const nextSteps = Array.isArray(extraction?.nextSteps)
    ? extraction.nextSteps.map((s) => String(s || '').trim()).filter(Boolean)
    : [];
  return { summary, nextSteps };
}

export async function waitForReview(getMemo, {
  intervalMs = 1500,
  timeoutMs = 180000,
  now = Date.now,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  const started = now();
  while (now() - started < timeoutMs) {
    const memo = await getMemo();
    const status = memoStatus(memo);
    if (isReviewReady(status) || status === 'approved') {
      return { ok: true, memo, status };
    }
    if (status === 'failed' || status === 'rejected') {
      return { ok: false, memo, status, error: memo?.errorMessage || 'Extraction failed' };
    }
    await sleep(intervalMs);
  }
  return { ok: false, error: 'Timed out waiting for extraction' };
}

export function reviewFields(preview) {
  const updates = Array.isArray(preview?.proposed_updates) ? preview.proposed_updates : [];
  return updates.filter((row) => row && row.field_name);
}
