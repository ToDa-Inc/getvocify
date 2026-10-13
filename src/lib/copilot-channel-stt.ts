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

export function hookMicPcm(
  ctx: AudioContext,
  stream: MediaStream,
  onPcm: (pcm: ArrayBuffer) => void,
): () => void {
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  proc.onaudioprocess = (event) => {
    onPcm(floatToPcm16(event.inputBuffer.getChannelData(0), ctx.sampleRate).buffer);
  };
  const mute = ctx.createGain();
  mute.gain.value = 0;
  source.connect(proc);
  proc.connect(mute);
  mute.connect(ctx.destination);
  return () => {
    try {
      source.disconnect();
      proc.disconnect();
    } catch {
      /* ignore */
    }
  };
}

export { LIVE_STT_SAMPLE_RATE };
