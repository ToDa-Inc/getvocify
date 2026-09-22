export const OVERLAY_WIDTH = 380;
export const OVERLAY_HEIGHT = 96;
export const OVERLAY_MARGIN = 16;

export function overlayBounds({ workArea } = {}) {
  const area = workArea || { x: 0, y: 0, width: 1440, height: 900 };
  return {
    width: OVERLAY_WIDTH,
    height: OVERLAY_HEIGHT,
    x: area.x + area.width - OVERLAY_WIDTH - OVERLAY_MARGIN,
    y: area.y + OVERLAY_MARGIN,
  };
}

export function trayMenuTemplate({ loggedIn = false, listening = false } = {}) {
  return [
    { id: 'show', label: 'Open Vocify' },
    { type: 'separator' },
    { id: 'listen', label: 'Listen', enabled: Boolean(loggedIn) && !listening },
    { id: 'stop', label: 'Stop & send', enabled: Boolean(listening) },
    { type: 'separator' },
    { id: 'dashboard', label: 'Open dashboard' },
    { type: 'separator' },
    { id: 'quit', label: 'Quit Vocify Companion' },
  ];
}

export function shouldQuitOnLastWindow({ platform = process.platform, isQuitting = false } = {}) {
  if (isQuitting) return true;
  return platform !== 'darwin';
}

export function dashboardOrigin(apiBase) {
  const base = String(apiBase || '').replace(/\/+$/, '');
  if (/localhost|127\.0\.0\.1/.test(base)) return 'http://localhost:8080';
  if (base.includes('api.getvocify.com')) return 'https://app.getvocify.com';
  return 'https://app.getvocify.com';
}

export function dashboardMemosUrl(apiBase) {
  return `${dashboardOrigin(apiBase)}/dashboard/memos`;
}

export function overlaySnippet(state = {}) {
  const interim = String(state.interimTranscript || '').trim();
  if (interim) return interim;
  const finalTranscript = String(state.finalTranscript || '').trim();
  if (!finalTranscript) return 'Listening to the call…';
  const parts = finalTranscript.split(/(?=(?:You|Them): )/).filter(Boolean);
  return (parts[parts.length - 1] || finalTranscript).trim();
}
