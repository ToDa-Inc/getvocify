/** Reserve and finalize server capture identity (POST /captures, POST /captures/:id/complete). */

const reserveInflight = new Map();

export async function reserveDesktopCapture(request, capture) {
  const clientCaptureId = String(capture.clientCaptureId || '').trim();
  if (!clientCaptureId) throw new Error('clientCaptureId required');
  if (capture.captureId) {
    return { capture_id: capture.captureId, memo_id: capture.memoId || capture.captureId };
  }
  if (reserveInflight.has(clientCaptureId)) {
    return reserveInflight.get(clientCaptureId);
  }
  const startedAt = capture.startedAt || new Date().toISOString();
  const job = request('/captures', {
    method: 'POST',
    body: {
      client_capture_id: clientCaptureId,
      started_at: startedAt,
      interaction_kind: 'meeting',
    },
  }).then((data) => {
    capture.captureId = data.capture_id;
    capture.memoId = data.memo_id;
    return data;
  }).finally(() => {
    reserveInflight.delete(clientCaptureId);
  });
  reserveInflight.set(clientCaptureId, job);
  return job;
}

export async function completeDesktopCapture(request, capture) {
  const captureId = String(capture.captureId || '').trim();
  if (!captureId) throw new Error('Capture not reserved');
  return request(`/captures/${encodeURIComponent(captureId)}/complete`, {
    method: 'POST',
    body: {
      transcript: capture.transcript ?? '',
      audio_duration: capture.duration ?? null,
      turns: capture.turns ?? [],
      transcript_complete: true,
    },
  });
}
