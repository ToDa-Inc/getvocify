import { LIVE_STT_SAMPLE_RATE, floatToPcm16 } from "@/features/recording/live-stt";
import type { MeetingSpeaker } from "@/lib/meeting-transcript";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8888/api/v1";
/** The live transcription service, apart from the API so nothing there can stall a call. */
const LIVE_API_URL = import.meta.env.VITE_LIVE_API_URL || API_URL;

/**
 * `echoCancel`: a meeting heard through the computer, so the server takes the call's echo out of the mic. "native": the
 * desktop app's own raw mic (the server also raises its level); "page": the page's mic, already leveled by the browser.
 */
export function liveTranscriptionWsUrl(userId: string, { echoCancel }: { echoCancel?: "native" | "page" } = {}): string {
  const ws = LIVE_API_URL.replace(/^http/, "ws").replace(/\/api\/v1\/?$/, "");
  const url = new URL(`${ws}/api/v1/transcription/live`);
  url.searchParams.set("user_id", userId);
  url.searchParams.set("mode", "copilot_channels");
  url.searchParams.set("channel_labels", "prospect,rep");
  url.searchParams.set("language", "multi");
  // Each side is checked against the profile's call languages and restarts in its own (ChannelReset).
  url.searchParams.set("detect", "1");
  if (echoCancel) url.searchParams.set("aec", "1");
  if (echoCancel === "page") url.searchParams.set("mic", "page");
  return url.toString();
}

/** The first message on a live socket: the ticket from POST /transcription/ticket. */
export function liveAuthMessage(ticket: string): string {
  return JSON.stringify({ type: "Auth", ticket });
}

export function encodeChannelAudio(channel: MeetingSpeaker, pcm: ArrayBuffer): string {
  const bytes = new Uint8Array(pcm);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return JSON.stringify({ type: "AddChannelAudio", channel, data: btoa(binary) });
}

/**
 * A stream's audio, gathered on the audio thread and handed over in 100 ms chunks. A busy page only delays the chunks;
 * it never loses them. (A ScriptProcessorNode runs on the page's own thread and drops whole buffers while the page is
 * busy, which it is on every transcript update: measured on a real recording, the mic delivered 95-97% of real time,
 * so its timing drifted against the call's and the server could not line the two up to take the echo out.)
 */
const PCM_TAP_SOURCE = `
class VocifyPcmTap extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = Math.round(sampleRate / 10);
    this.buffer = new Float32Array(this.size);
    this.filled = 0;
  }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    let at = 0;
    while (at < input.length) {
      const take = Math.min(input.length - at, this.size - this.filled);
      this.buffer.set(input.subarray(at, at + take), this.filled);
      this.filled += take;
      at += take;
      if (this.filled === this.size) {
        this.port.postMessage(this.buffer, [this.buffer.buffer]);
        this.buffer = new Float32Array(this.size);
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor("vocify-pcm-tap", VocifyPcmTap);
`;

const tapModules = new WeakMap<BaseAudioContext, Promise<void>>();

function loadPcmTap(ctx: BaseAudioContext): Promise<void> {
  let loading = tapModules.get(ctx);
  if (!loading) {
    const url = URL.createObjectURL(new Blob([PCM_TAP_SOURCE], { type: "application/javascript" }));
    loading = ctx.audioWorklet.addModule(url).finally(() => URL.revokeObjectURL(url));
    tapModules.set(ctx, loading);
  }
  return loading;
}

export function hookMicPcm(
  ctx: AudioContext,
  stream: MediaStream,
  onPcm: (pcm: ArrayBuffer) => void,
): () => void {
  const source = ctx.createMediaStreamSource(stream);
  // Nothing pulls a node that leads nowhere: the tap ends in a muted gain, so the audio never plays back.
  const mute = ctx.createGain();
  mute.gain.value = 0;
  mute.connect(ctx.destination);
  let tap: AudioWorkletNode | null = null;
  let released = false;
  void loadPcmTap(ctx).then(
    () => {
      if (released) return;
      tap = new AudioWorkletNode(ctx, "vocify-pcm-tap", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      tap.port.onmessage = (event: MessageEvent<Float32Array>) => onPcm(floatToPcm16(event.data, ctx.sampleRate).buffer as ArrayBuffer);
      source.connect(tap);
      tap.connect(mute);
    },
    (error) => console.error("Vocify: the audio tap could not load", error),
  );
  return () => {
    released = true;
    try {
      source.disconnect();
      tap?.disconnect();
      mute.disconnect();
    } catch {
      /* ignore */
    }
  };
}

export { LIVE_STT_SAMPLE_RATE };
