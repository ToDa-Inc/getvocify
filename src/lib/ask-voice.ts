export type VoiceComposerState = {
  composer_state: "idle" | "recording" | "transcribing" | "ready_to_send" | "permission_denied";
  text: string;
  auto_send: false;
  sent: boolean;
  mic_released: boolean;
  timer_running: boolean;
  elapsed_ms: number;
  panel_blocked: false;
  memo_id: null;
};

export function idleVoice(): VoiceComposerState {
  return {
    composer_state: "idle",
    text: "",
    auto_send: false,
    sent: false,
    mic_released: true,
    timer_running: false,
    elapsed_ms: 0,
    panel_blocked: false,
    memo_id: null,
  };
}

export function startRecording(view: VoiceComposerState): VoiceComposerState {
  return {
    ...view,
    composer_state: "recording",
    timer_running: true,
    mic_released: false,
    sent: false,
    auto_send: false,
    memo_id: null,
    panel_blocked: false,
  };
}

export function cancelVoice(
  view: VoiceComposerState,
  options?: { silence?: boolean },
): VoiceComposerState {
  void options;
  return {
    ...idleVoice(),
    sent: false,
    mic_released: true,
  };
}

export function stopRecording(view: VoiceComposerState, elapsedMs: number): VoiceComposerState {
  return {
    ...view,
    composer_state: "transcribing",
    timer_running: false,
    elapsed_ms: elapsedMs,
    mic_released: true,
    sent: false,
    auto_send: false,
    memo_id: null,
    panel_blocked: false,
  };
}

export function transcriptionReady(view: VoiceComposerState, text: string): VoiceComposerState {
  return {
    ...view,
    composer_state: "ready_to_send",
    text,
    auto_send: false,
    sent: false,
    mic_released: true,
    timer_running: false,
    memo_id: null,
    panel_blocked: false,
  };
}

export function permissionDenied(view: VoiceComposerState): VoiceComposerState {
  return {
    ...view,
    composer_state: "permission_denied",
    mic_released: true,
    timer_running: false,
    sent: false,
    panel_blocked: false,
    memo_id: null,
    auto_send: false,
  };
}
