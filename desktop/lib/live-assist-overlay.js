function normalizeEvidenceRefs(value) {
  if (!Array.isArray(value)) return [];
  const refs = [];
  for (const item of value) {
    if (typeof item !== 'string') continue;
    const trimmed = item.trim();
    if (trimmed) refs.push(trimmed);
  }
  return refs;
}

function resolveKind(kind) {
  return kind === 'meeting' || kind === 'call' ? kind : null;
}

function suggestResultText(event) {
  if (!event || typeof event !== 'object') return '';
  if (typeof event.text === 'string') return event.text.trim();
  const suggestion = event.suggestion && typeof event.suggestion === 'object' ? event.suggestion : null;
  if (!suggestion) return '';
  if (typeof suggestion.text === 'string') return suggestion.text.trim();
  if (typeof suggestion.say_this === 'string') return suggestion.say_this.trim();
  return '';
}

function suggestObjectionCategory(event) {
  const suggestion = event?.suggestion && typeof event.suggestion === 'object' ? event.suggestion : null;
  if (!suggestion) return null;
  const raw = suggestion.objection_type ?? suggestion.objectionType ?? null;
  if (raw == null || raw === '') return null;
  return String(raw).trim() || null;
}

/** Map a copilot suggest SSE `result` event into overlay payload fields. */
export function liveAssistPayloadFromSuggestEvent(event) {
  if (!event || event.type !== 'result') return null;
  const category = suggestObjectionCategory(event);
  return {
    playbook_ready: event.playbook_ready === true,
    evidence_refs: event.evidence_refs,
    text: suggestResultText(event),
    category,
  };
}

/**
 * Map a copilot suggest/result payload into overlay live-assist fields.
 * Never invents card text or evidence refs.
 */
export function liveAssistOverlayFromCopilotPayload(payload, { kind } = {}) {
  const base = {
    kind: resolveKind(kind),
    playbookReady: false,
    evidenceRefs: [],
    card: null,
  };

  if (!payload || typeof payload !== 'object') {
    return base;
  }

  base.playbookReady = payload.playbook_ready === true;
  base.evidenceRefs = normalizeEvidenceRefs(payload.evidence_refs);

  if (!base.evidenceRefs.length) {
    base.card = null;
    return base;
  }

  const text = typeof payload.text === 'string' ? payload.text.trim() : '';
  const category =
    payload.category != null && String(payload.category).trim()
      ? String(payload.category).trim()
      : null;
  base.card = text ? { text, category } : null;
  return base;
}
