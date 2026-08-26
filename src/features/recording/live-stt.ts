/**
 * Dashboard live STT helpers.
 *
 * The record widget both MediaRecords the mic and streams PCM over WebSocket.
 * Those two graphs must not share the same MediaStreamTrack, and PCM must be
 * 16 kHz s16le regardless of the AudioContext's actual sample rate.
 */

export const LIVE_STT_SAMPLE_RATE = 16000;

export type TranscriptPiece = {
  interim: string;
  final: string;
  full: string;
};

export const EMPTY_TRANSCRIPT: TranscriptPiece = {
  interim: "",
  final: "",
  full: "",
};

export function cloneAudioTracks<T extends { clone: () => T }>(
  stream: { getAudioTracks: () => T[] },
): T[] {
  return stream.getAudioTracks().map((track) => track.clone());
}

export function cloneAudioStream(stream: MediaStream): MediaStream {
  return new MediaStream(cloneAudioTracks(stream));
}

export function stopMediaStream(stream: MediaStream | null | undefined): void {
  if (!stream) return;
  stream.getTracks().forEach((track) => {
    try {
      track.stop();
    } catch {
      /* ignore */
    }
  });
}

export function downsampleTo16k(input: Float32Array, sourceRate: number): Float32Array {
  const rate = Number(sourceRate) || LIVE_STT_SAMPLE_RATE;
  if (!input.length || rate === LIVE_STT_SAMPLE_RATE) return input;
  if (rate < LIVE_STT_SAMPLE_RATE) return input;
  const ratio = rate / LIVE_STT_SAMPLE_RATE;
  const outLen = Math.floor(input.length / ratio);
  if (outLen <= 0) return new Float32Array(0);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let j = start; j < end && j < input.length; j++) {
      sum += input[j];
      count += 1;
    }
    out[i] = count ? sum / count : 0;
  }
  return out;
}

export function floatToPcm16(input: Float32Array, sourceRate: number): Int16Array {
  const samples = downsampleTo16k(input, sourceRate);
  const int16 = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16;
}

type LiveWord = { text?: string; is_punct?: boolean };

export function applyLiveResults(
  prev: TranscriptPiece,
  data: {
    type?: string;
    channel?: { alternatives?: Array<{ transcript?: string }> };
    is_final?: boolean;
    speech_final?: boolean;
    words?: LiveWord[];
  },
): TranscriptPiece | null {
  if (data?.type !== "Results") return null;

  const transcript = data.channel?.alternatives?.[0]?.transcript || "";
  const words = Array.isArray(data.words) ? data.words : [];
  if (!transcript && words.length === 0) return null;

  const isFinal = Boolean(data.is_final || data.speech_final);
  const piece =
    transcript ||
    words
      .filter((w) => !w.is_punct)
      .map((w) => String(w.text || ""))
      .filter(Boolean)
      .join(" ");

  let nextFinal = prev.final;
  let nextInterim = prev.interim;

  if (isFinal) {
    if (piece) nextFinal = nextFinal ? `${nextFinal} ${piece}` : piece;
    nextInterim = "";
  } else {
    nextInterim = piece || transcript;
  }

  return {
    final: nextFinal,
    interim: nextInterim,
    full: `${nextFinal}${nextInterim ? ` ${nextInterim}` : ""}`.trim(),
  };
}

/** AudioWorklet source: PCM s16le at 16 kHz, independent of context sampleRate. */
export const PCM_WORKLET_SOURCE = `
const TARGET_RATE = ${LIVE_STT_SAMPLE_RATE};
class PcmProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input.length || !input[0] || !input[0].length) return true;
    const channelData = input[0];
    const rate = sampleRate || TARGET_RATE;
    const ratio = rate / TARGET_RATE;
    const outLen = ratio <= 1 ? channelData.length : Math.floor(channelData.length / ratio);
    if (outLen <= 0) return true;
    const int16Array = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      let sample;
      if (ratio <= 1) {
        sample = channelData[i];
      } else {
        const start = Math.floor(i * ratio);
        const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
        let sum = 0;
        let count = 0;
        for (let j = start; j < end && j < channelData.length; j++) {
          sum += channelData[j];
          count += 1;
        }
        sample = count ? sum / count : 0;
      }
      const s = Math.max(-1, Math.min(1, sample));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    this.port.postMessage(int16Array.buffer, [int16Array.buffer]);
    return true;
  }
}
registerProcessor('pcm-processor', PcmProcessor);
`;
