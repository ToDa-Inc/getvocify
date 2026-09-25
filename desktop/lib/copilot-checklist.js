export function buildCopilotChecklistRequestBody({ session = {} } = {}) {
  const body = { call_mode: 'meeting' };
  const captureId = String(session.captureId ?? session.capture_id ?? '').trim();
  if (captureId) body.capture_id = captureId;
  return body;
}

export async function fetchCopilotChecklist(
  fetchImpl,
  { apiBase, token, body, signal } = {},
) {
  const base = String(apiBase || '').replace(/\/+$/, '');
  const res = await fetchImpl(`${base}/copilot/checklist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    return { ok: false, status: res.status, data: null };
  }
  const data = await res.json().catch(() => null);
  if (!data || typeof data !== 'object') {
    return { ok: false, status: res.status, data: null };
  }
  return { ok: true, status: res.status, data };
}
