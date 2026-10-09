import { initialPillState, pillDecision } from '../shared/ui/copilot/pill.js';

export { initialPillState };

export function speakerRoleFromInterim(interimTranscript) {
  const line = String(interimTranscript ?? '').trim();
  if (line.startsWith('You:')) return 'rep';
  if (line.startsWith('Them:')) return 'prospect';
  return null;
}

export function copilotSuggestionCategory(suggestion) {
  if (!suggestion || typeof suggestion !== 'object') return null;
  const raw = suggestion.objection_type ?? suggestion.objectionType ?? null;
  if (raw == null || raw === '') return null;
  const trimmed = String(raw).trim();
  return trimmed || null;
}

export function buildCopilotPillInput({ state, meetingId } = {}) {
  const suggestion = state?.copilotSuggestion;
  return {
    kind: 'meeting',
    enabled: state?.assistEnabled === true,
    speakerRole: speakerRoleFromInterim(state?.interimTranscript),
    text: suggestion?.say_this ?? '',
    category: copilotSuggestionCategory(suggestion),
    meetingId: meetingId ?? null,
  };
}

/** @returns {{ show: boolean, text: string, state: ReturnType<typeof initialPillState> }} */
export function decideCopilotPillLine(pillState, state, meetingId, now) {
  const decision = pillDecision(
    pillState ?? initialPillState(),
    buildCopilotPillInput({ state, meetingId }),
    now,
  );
  return {
    show: Boolean(decision.show),
    text: decision.text ?? '',
    state: decision.state,
  };
}
