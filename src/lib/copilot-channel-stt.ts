import { LIVE_STT_SAMPLE_RATE, floatToPcm16 } from "@/features/recording/live-stt";
import type { MeetingSpeaker } from "@/lib/meeting-transcript";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8888/api/v1";

export function liveTranscriptionWsUrl(userId: string): string {
  const ws = API_URL.replace(/^http/, "ws").replace(/\/api\/v1\/?$/, "");
  const url = new URL(`${ws}/api/v1/transcription/live`);
  url.searchParams.set("user_id", userId);
  url.searchParams.set("mode", "copilot_channels");
  url.searchParams.set("channel_labels", "prospect,rep");
  url.searchParams.set("language", "multi");
  // Each side is checked against the profile's call languages and restarts in its own (ChannelReset).
  url.searchParams.set("detect", "1");
  return url.toString();
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
