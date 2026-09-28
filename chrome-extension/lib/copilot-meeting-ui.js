import { strings } from '../shared/ui/i18n.js';

export function isMeetingListenActive(state) {
  const listening =
    Boolean(state?.isCopilotListening)
    || state?.listenPhase === 'starting'
    || state?.listenPhase === 'live'
    || state?.status === 'copilot';
  return listening && state?.callMode === 'meeting';
}

export function copilotAssistToggleLabel(assistEnabled, lang) {
  const t = strings(lang);
  return assistEnabled ? t.helpOff : t.helpOn;
}

export function shouldShowCopilotChecklist(state, checklist) {
  if (!isMeetingListenActive(state)) return false;
  if (!checklist || typeof checklist !== 'object') return false;
  const applicable = Number(checklist.applicable);
  return Number.isFinite(applicable) && applicable > 0;
}
