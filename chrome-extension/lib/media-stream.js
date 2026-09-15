/**
 * Mic capture helpers shared by offscreen recording and its tests.
 * Dashboard live STT clones tracks for the same reason: MediaRecorder and
 * the PCM worklet must not share one MediaStreamTrack.
 */

export const MIN_MIC_DURATION_MS = 5000;
export const MIN_MIC_BYTES = 8000;

export function cloneAudioTracks(stream) {
  const tracks = stream?.getAudioTracks?.() || [];
  return tracks.map((track) => track.clone());
}

export function cloneAudioStream(stream) {
  return new MediaStream(cloneAudioTracks(stream));
}

export function isUsableMicRecording({ durationMs = 0, byteLength = 0 } = {}) {
  if (Number(durationMs) < MIN_MIC_DURATION_MS) {
    return { ok: false, reason: 'too_short' };
  }
  if (Number(byteLength) < MIN_MIC_BYTES) {
    return { ok: false, reason: 'invalid_audio' };
  }
  return { ok: true, reason: null };
}
