export function isMeetingListenActive(state) {
  const listening =
    Boolean(state?.isCopilotListening)
    || state?.listenPhase === 'starting'
    || state?.listenPhase === 'live'
    || state?.status === 'copilot';
  return listening && state?.callMode === 'meeting';
}

export function copilotAssistToggleLabel(assistEnabled) {
  return assistEnabled ? 'Ocultar ayuda' : 'Ayuda';
}

export function shouldShowCopilotChecklist(state, checklist) {
  if (!isMeetingListenActive(state)) return false;
  if (!checklist || typeof checklist !== 'object') return false;
  const applicable = Number(checklist.applicable);
  return Number.isFinite(applicable) && applicable > 0;
}
