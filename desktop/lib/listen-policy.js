export function canStartListen({ hasToken = false, isListening = false } = {}) {
  if (isListening) return { ok: false, reason: 'already_listening' };
  if (!hasToken) return { ok: false, reason: 'login_required' };
  return { ok: true };
}

export function startDeniedMessage(reason) {
  switch (reason) {
    case 'already_listening':
      return 'Already listening.';
    case 'login_required':
      return 'Log in to start listening.';
    case 'no_system_audio':
      return 'Could not capture system audio. On macOS grant Screen Recording, then try again.';
    case 'no_mic':
      return 'Microphone permission is required for your side of the call.';
    default:
      return 'Could not start listening.';
  }
}

export function applyTranscriptUpdate(state, { text, isFinal, audioChannel } = {}) {
  const finalTranscript = state.finalTranscript || '';
  const piece = typeof text === 'string' ? text : '';
  const role = audioChannel === 'rep' ? 'rep' : audioChannel === 'prospect' ? 'prospect' : null;
  const tagged = !piece
    ? ''
    : role === 'rep'
      ? `You: ${piece}`
      : role === 'prospect'
        ? `Them: ${piece}`
        : piece;

  if (isFinal) {
    return {
      finalTranscript: tagged ? (finalTranscript ? `${finalTranscript} ${tagged}` : tagged) : finalTranscript,
      interimTranscript: '',
    };
  }
  return {
    finalTranscript,
    interimTranscript: tagged || piece,
  };
}
