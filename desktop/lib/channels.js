export const COPILOT_CHANNEL_MODE = 'copilot_channels';
export const CHANNEL_PROSPECT = 'prospect';
export const CHANNEL_REP = 'rep';

export function parseChannelLabels(raw) {
  if (raw == null || String(raw).trim() === '') return [CHANNEL_PROSPECT, CHANNEL_REP];
  const out = [];
  for (const part of String(raw).split(',')) {
    const p = part.trim().toLowerCase();
    if ((p === CHANNEL_PROSPECT || p === CHANNEL_REP) && !out.includes(p)) out.push(p);
    if (out.length === 2) break;
  }
  return out.length ? out : [CHANNEL_PROSPECT];
}

export function encodeChannelAudio(channel, pcmBuffer) {
  const bytes = new Uint8Array(pcmBuffer);
  let data;
  if (typeof Buffer !== 'undefined') {
    data = Buffer.from(bytes).toString('base64');
  } else {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    data = btoa(binary);
  }
  return JSON.stringify({
    type: 'AddChannelAudio',
    channel,
    data,
  });
}

export function applyChannelLabelsToLiveUrl(wsUrl, labels) {
  const parsed = Array.isArray(labels)
    ? parseChannelLabels(labels.join(','))
    : parseChannelLabels(labels);
  const url = new URL(wsUrl);
  url.searchParams.set('mode', COPILOT_CHANNEL_MODE);
  url.searchParams.set('channel_labels', parsed.join(','));
  return url.toString();
}

export function apiBaseToWsOrigin(apiBase) {
  const http = String(apiBase || '').replace(/\/+$/, '');
  const ws = http.replace(/^https:/i, 'wss:').replace(/^http:/i, 'ws:');
  return ws.replace(/\/api\/v1$/i, '');
}

export function liveTranscriptionUrl(apiBase, language = 'multi') {
  return `${apiBaseToWsOrigin(apiBase)}/api/v1/transcription/live?language=${encodeURIComponent(language)}`;
}
