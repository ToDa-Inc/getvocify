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
  base.card = text ? { text } : null;
  return base;
}
