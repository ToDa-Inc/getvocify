import { strings } from '../renderer/shared/ui/i18n.js';

export const OVERLAY_WIDTH = 380;
export const OVERLAY_HEIGHT = 96;
export const OVERLAY_MARGIN = 16;
const OVERLAY_CHECKLIST_SUMMARY = 22;
const OVERLAY_CHECKLIST_STEP = 18;

export const WINDOW_SIZE = {
  compact: { width: 440, height: 780 },
  review: { width: 920, height: 780 },
};

export function overlayBounds({ workArea } = {}) {
  const area = workArea || { x: 0, y: 0, width: 1440, height: 900 };
  return {
    width: OVERLAY_WIDTH,
    height: OVERLAY_HEIGHT,
    x: area.x + area.width - OVERLAY_WIDTH - OVERLAY_MARGIN,
    y: area.y + OVERLAY_MARGIN,
  };
}

export function overlayChecklistExtraHeight(checklist, kind) {
  if (kind !== 'meeting' || !checklist || typeof checklist !== 'object') return 0;
  const applicable = Number(checklist.applicable);
  if (!Number.isFinite(applicable) || applicable <= 0) return 0;
  const steps = Array.isArray(checklist.steps) ? checklist.steps.length : 0;
  return OVERLAY_CHECKLIST_SUMMARY + steps * OVERLAY_CHECKLIST_STEP;
}

export function overlayBoundsForState(state = {}, { workArea } = {}) {
  const base = overlayBounds({ workArea });
  const overlay = overlayShellState(state);
  const extra = overlayChecklistExtraHeight(overlay.checklist, overlay.kind);
  if (!extra) return base;
  return { ...base, height: OVERLAY_HEIGHT + extra };
}

export function trayMenuTemplate({ loggedIn = false, listening = false } = {}) {
  return [
    { id: 'show', label: 'Open Vocify' },
    { type: 'separator' },
    { id: 'listen', label: 'Listen', enabled: Boolean(loggedIn) && !listening },
    { id: 'stop', label: 'Stop & review', enabled: Boolean(listening) },
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

export function overlaySnippet(state = {}, lang) {
  const interim = String(state.interimTranscript || '').trim();
  if (interim) return interim;
  const finalTranscript = String(state.finalTranscript || '').trim();
  if (!finalTranscript) return strings(lang).overlayListening;
  const parts = finalTranscript.split(/(?=(?:You|Them): )/).filter(Boolean);
  return (parts[parts.length - 1] || finalTranscript).trim();
}

/** Fields the overlay pill needs for live assist; never fabricates card text. */
export function assistOverlayFields(assist = {}) {
  const out = {
    evidenceRefs: Array.isArray(assist.evidenceRefs) ? [...assist.evidenceRefs] : [],
  };
  if (assist.kind === 'call' || assist.kind === 'meeting') {
    out.kind = assist.kind;
  } else if (Object.prototype.hasOwnProperty.call(assist, 'kind')) {
    out.kind = null;
  }
  if (typeof assist.playbookReady === 'boolean') {
    out.playbookReady = assist.playbookReady;
  } else if (Object.prototype.hasOwnProperty.call(assist, 'playbookReady')) {
    out.playbookReady = null;
  }
  if (assist.assistEnabled !== undefined) {
    out.assistEnabled = assist.assistEnabled;
  } else if (Object.prototype.hasOwnProperty.call(assist, 'assistEnabled')) {
    out.assistEnabled = null;
  }
  if (assist.card != null && typeof assist.card === 'object') {
    out.card = assist.card;
  } else if (Object.prototype.hasOwnProperty.call(assist, 'card')) {
    out.card = null;
  }
  return out;
}

export function overlayShellState(state = {}) {
  const lastLine =
    state.lastLine != null && String(state.lastLine).length
      ? String(state.lastLine)
      : overlaySnippet(state);
  const overlay = {
    listening: Boolean(state.listening),
    lastLine,
  };
  const assist = assistOverlayFields(state);
  if (assist.kind != null) overlay.kind = assist.kind;
  if (typeof assist.playbookReady === 'boolean') overlay.playbookReady = assist.playbookReady;
  if (assist.assistEnabled !== undefined && assist.assistEnabled !== null) {
    overlay.assistEnabled = assist.assistEnabled;
  }
  overlay.evidenceRefs = assist.evidenceRefs;
  if (assist.card != null) overlay.card = assist.card;
  if (state.checklist != null && typeof state.checklist === 'object') {
    overlay.checklist = state.checklist;
  }
  if (state.meetingId != null && String(state.meetingId).length) {
    overlay.meetingId = String(state.meetingId);
  }
  return overlay;
}
