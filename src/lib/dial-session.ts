import { CALL_STATES, type CallState } from "./dial-target.ts";

export type VoiceClient = "twilio" | "telnyx";

export type SipHeader = { name: string; value: string };

export function voiceClientFromToken(provider?: string | null): VoiceClient {
  return provider === "telnyx" ? "telnyx" : "twilio";
}

export function vocifyCallHeaders(args: {
  callerId?: string | number | null;
  contactId?: string | number | null;
  dealId?: string | number | null;
}): SipHeader[] {
  const headers: SipHeader[] = [];
  if (args.callerId) {
    headers.push({ name: "X-Vocify-Caller-Id", value: String(args.callerId) });
  }
  if (args.contactId) {
    headers.push({ name: "X-Vocify-Contact-Id", value: String(args.contactId) });
  }
  if (args.dealId) {
    headers.push({ name: "X-Vocify-Deal-Id", value: String(args.dealId) });
  }
  return headers;
}

export const TELNYX_RINGBACK_SRC = "/call-ringback.wav";
/** PSTN dial timeout is 30s; cap local tone so a missed hangup cannot loop for minutes. */
export const TELNYX_RING_TIMEOUT_MS = 35_000;

export function ringbackTimedOut(
  startedAt: number,
  now: number,
  maxMs = TELNYX_RING_TIMEOUT_MS,
): boolean {
  return now - startedAt >= maxMs;
}

export function telnyxRtcClientOptions(token: string, ringbackFile = TELNYX_RINGBACK_SRC) {
  return { login_token: token, ringbackFile };
}

export function startLocalRingback(
  src = TELNYX_RINGBACK_SRC,
  maxMs = TELNYX_RING_TIMEOUT_MS,
): () => void {
  const audio = new Audio(src);
  audio.loop = true;
  void audio.play().catch(() => {
    /* autoplay can still lose if the click gesture already settled */
  });
  let timer = 0;
  const stop = () => {
    window.clearTimeout(timer);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  };
  timer = window.setTimeout(stop, maxMs);
  return stop;
}

export function watchRemoteAudio(
  remote: HTMLAudioElement,
  onAudio: () => void,
): () => void {
  let stopped = false;
  let raf = 0;
  let ctx: AudioContext | null = null;
  let loudFrames = 0;
  const data = new Uint8Array(256);

  const hook = () => {
    if (stopped) return;
    const stream = remote.srcObject;
    if (!(stream instanceof MediaStream)) {
      raf = window.setTimeout(hook, 150) as unknown as number;
      return;
    }
    ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const tick = () => {
      if (stopped) return;
      analyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
      // Parked WebRTC answers immediately; ignore connect pops. Real speech
      // or server ringback stays loud for ~200ms.
      if (peak > 20) {
        loudFrames += 1;
        if (loudFrames >= 12) {
          onAudio();
          return;
        }
      } else {
        loudFrames = 0;
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
  };
  hook();
  return () => {
    stopped = true;
    window.clearTimeout(raf);
    cancelAnimationFrame(raf);
    void ctx?.close();
  };
}

export function telnyxNewCallOptions(args: {
  to: string;
  callerId?: string | number | null;
  contactId?: string | number | null;
  dealId?: string | number | null;
}): {
  destinationNumber: string;
  audio: true;
  customHeaders: SipHeader[];
} {
  return {
    destinationNumber: args.to,
    audio: true,
    customHeaders: vocifyCallHeaders(args),
  };
}

const RINGING = new Set(["ringing", "early", "trying", "requesting", "recovering"]);
const ACTIVE = new Set(["active", "held"]);
const IDLE = new Set(["hangup", "destroy", "destroyed", "purge"]);

export function dispositionMessage(disposition?: string | null): string | null {
  const value = String(disposition || "").toLowerCase();
  if (value === "busy") return "Ocupado";
  if (value === "no_answer" || value === "no-answer" || value === "no_response") {
    return "Sin respuesta";
  }
  if (value === "canceled" || value === "cancelled") return "Llamada cancelada";
  if (value === "failed") return "Llamada fallida";
  return null;
}
export function telnyxHangupMessage(call: {
  sipCode?: number | string | null;
  sipReason?: string | null;
  causeCode?: number | string | null;
  cause?: string | null;
  hangupCause?: string | null;
} | null | undefined): string | null {
  const sip = Number(call?.sipCode);
  const q850 = Number(call?.causeCode);
  const cause = [call?.cause, call?.hangupCause, call?.sipReason]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (sip === 486 || q850 === 17 || cause.includes("busy")) {
    return "Ocupado";
  }
  if (
    sip === 480 ||
    sip === 408 ||
    q850 === 18 ||
    q850 === 19 ||
    cause.includes("timeout") ||
    cause.includes("no_answer") ||
    cause.includes("no answer")
  ) {
    return "Sin respuesta";
  }
  if (sip === 603 || sip === 487 || cause.includes("reject")) {
    return "Llamada rechazada";
  }
  return null;
}

export function mapTelnyxCallState(raw: unknown): CallState {
  const state = String(raw || "").toLowerCase();
  if (ACTIVE.has(state)) return CALL_STATES.ACTIVE;
  if (RINGING.has(state)) return CALL_STATES.RINGING;
  if (IDLE.has(state)) return CALL_STATES.IDLE;
  return CALL_STATES.CONNECTING;
}
