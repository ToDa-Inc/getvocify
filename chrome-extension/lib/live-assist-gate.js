/**
 * Map copilot suggest SSE / result payloads to live-assist card gate inputs.
 * Does not invent evidence refs — only passes through server-provided values.
 */

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

function playbookReadyFrom(source) {
  if (!source || typeof source !== 'object') return false;
  if (source.playbook_ready === true || source.playbookReady === true) return true;
  if (source.playbook === true || source.has_playbook === true) return true;
  if (source.grounded === true) return true;
  const versionId = source.playbook_version_id ?? source.playbookVersionId;
  if (typeof versionId === 'string' && versionId.trim()) return true;
  return false;
}

function evidenceRefsFrom(source) {
  if (!source || typeof source !== 'object') return [];
  return normalizeEvidenceRefs(source.evidence_refs ?? source.evidenceRefs);
}

/**
 * @param {Record<string, unknown> | null | undefined} payload SSE event or suggest body
 * @returns {{ playbookReady: boolean, evidenceRefs: string[] }}
 */
export function liveAssistGateFromSuggestPayload(payload) {
  if (!payload || typeof payload !== 'object') {
    return { playbookReady: false, evidenceRefs: [] };
  }

  const suggestion =
    payload.suggestion && typeof payload.suggestion === 'object' ? payload.suggestion : null;
  const sources = [payload, suggestion].filter(Boolean);

  let playbookReady = false;
  let evidenceRefs = [];

  for (const source of sources) {
    if (playbookReadyFrom(source)) playbookReady = true;
    const refs = evidenceRefsFrom(source);
    if (refs.length) evidenceRefs = refs;
  }

  return { playbookReady, evidenceRefs };
}
