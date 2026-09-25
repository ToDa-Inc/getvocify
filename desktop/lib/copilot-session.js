/** Pure live-assist session helpers for the desktop listen renderer (no fetch / mic). */

export function emptyLiveAssistOverlay() {
  return {
    kind: null,
    playbookReady: null,
    assistEnabled: false,
    evidenceRefs: [],
    card: null,
  };
}

export function beginMeetingListenAssist({ createMeetingId }) {
  const meetingId =
    typeof createMeetingId === "function" ? createMeetingId() : `meet-${Date.now()}`;
  return {
    meetingId,
    overlay: {
      assistEnabled: false,
      card: null,
      evidenceRefs: [],
      playbookReady: null,
      kind: "meeting",
    },
    checklist: null,
    resetSuggestDedupe: true,
  };
}

export function turnOffLiveAssist(overlay) {
  if (!overlay || typeof overlay !== "object") return { shouldAbortSuggest: true };
  overlay.assistEnabled = false;
  overlay.card = null;
  return { shouldAbortSuggest: true };
}

export function resetLiveAssistOnStop() {
  return {
    meetingId: null,
    overlay: emptyLiveAssistOverlay(),
    checklist: null,
    shouldAbortSuggest: true,
    shouldAbortChecklist: true,
    resetSuggestDedupe: true,
  };
}

export function shouldApplyCopilotStreamPayload({ signalAborted }) {
  return signalAborted !== true;
}

export function shouldRequestLiveCopilotSuggest({
  listening,
  assistEnabled,
  hasToken,
  latestTurn,
  shouldRequestTurn,
}) {
  if (assistEnabled !== true) return false;
  if (!listening || !hasToken) return false;
  return Boolean(shouldRequestTurn?.(latestTurn));
}
