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

export async function fetchVoiceTokenAfterRingback<T>(
  startRingback: () => () => void,
  fetchToken: () => Promise<T>,
): Promise<{ token: T; stop: () => void }> {
  const stop = startRingback();
  try {
    return { token: await fetchToken(), stop };
  } catch (error) {
    stop();
    throw error;
  }
}

export function startLocalRingback(
  src = TELNYX_RINGBACK_SRC,
  maxMs = TELNYX_RING_TIMEOUT_MS,
  createAudio: (url: string) => HTMLAudioElement = (url) => new Audio(url),
): () => void {
  const audio = createAudio(src);
  audio.loop = true;
  const played = audio.play();
  if (played && typeof played.catch === "function") {
    void played.catch((err) => {
      console.warn("vocify ringback play failed", err);
    });
  }
  let timer: ReturnType<typeof setTimeout> | 0 = 0;
  const stop = () => {
    clearTimeout(timer);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  };
  timer = setTimeout(stop, maxMs);
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

/** Twilio Voice SDK 31005 after Dial hangs up the parent leg — not a Voice URL miss. */
export function isCarrierHangupError(error: unknown): boolean {
  if (error && typeof error === "object" && Number((error as { code?: number }).code) === 31005) {
    return true;
  }
  const text = String(error || "");
  return /\b31005\b/.test(text) || /error sent from gateway in hangup/i.test(text);
}

/**
 * Voice JS SDK maps a gateway HANGUP `{code:31000,message:General Error}` to
 * UnknownError. Same string for Dial timeout and for PSTN `failed` (e.g. 13227).
 * Hide the raw SDK copy; map from DialCallStatus instead.
 */
export function isVoiceSdkGeneralError(error: unknown): boolean {
  if (error && typeof error === "object" && Number((error as { code?: number }).code) === 31000) {
    return true;
  }
  return /\b31000\b/.test(String(error || ""));
}

const VOICE_TOKEN_CODES = new Set([20101, 20104, 20105, 31204, 31205]);

function errorText(error: unknown): string {
  if (!error) return "";
  if (typeof error === "string") return error;
  const err = error as { message?: string; data?: { detail?: string } };
  return String(err.message || err.data?.detail || error);
}

/** Twilio Voice JWT dead or not yet valid — minting a new one + new Device fixes it. */
export function isVoiceAccessTokenError(error: unknown): boolean {
  const code = error && typeof error === "object" ? Number((error as { code?: number }).code) : NaN;
  if (VOICE_TOKEN_CODES.has(code)) return true;
  const text = errorText(error);
  return (
    /\b(20101|20104|20105|31204|31205)\b/.test(text)
    || /access.?token/i.test(text)
    || /jwt token (expired|invalid)/i.test(text)
  );
}

/**
 * Device.connect() can throw 20104 while the JWT we just minted is fine: the
 * reused Device is still holding a dead token. Remint + force a new Device once.
 */
export async function connectWithVoiceTokenRecovery<T>(args: {
  token: string;
  connect: (token: string, forceNew: boolean) => Promise<T>;
  remint: () => Promise<string>;
}): Promise<T> {
  try {
    return await args.connect(args.token, false);
  } catch (error) {
    if (!isVoiceAccessTokenError(error)) throw error;
    const next = await args.remint();
    return args.connect(next, true);
  }
}

/** tokenWillExpire: push a new JWT, or tear the Device down so the next click is clean. */
export async function applyVoiceTokenRefresh(args: {
  remint: () => Promise<string>;
  apply: (token: string) => void;
  onFailure: () => void;
}): Promise<void> {
  try {
    args.apply(await args.remint());
  } catch {
    args.onFailure();
  }
}

export function isExtensionRuntimeError(error: unknown): boolean {
  const text = errorText(error);
  return (
    /receiving end does not exist/i.test(text)
    || /message port closed/i.test(text)
    || /extension context invalidated/i.test(text)
    || /service worker/i.test(text)
    || /worker service/i.test(text)
  );
}

export function isVocifySessionError(error: unknown): boolean {
  if (error && typeof error === "object" && Number((error as { status?: number }).status) === 401) {
    return true;
  }
  return /session expired|invalid or expired session|please sign in/i.test(errorText(error));
}

export const CALL_ERROR_TOKEN_STALE = "La sesión de llamada caducó. Pulsa Llamar otra vez.";
export const CALL_ERROR_EXTENSION_RESTARTED = "Vocify se reinició. Pulsa Llamar otra vez.";
export const CALL_ERROR_SESSION = "Tu sesión de Vocify caducó. Recarga la extensión.";
export const CALL_ERROR_START = "No se pudo iniciar la llamada.";

export function userFacingCallError(error: unknown, fallback = CALL_ERROR_START): string | null {
  if (isCarrierHangupError(error) || isVoiceSdkGeneralError(error)) return null;
  if (isVocifySessionError(error)) return CALL_ERROR_SESSION;
  if (isExtensionRuntimeError(error)) return CALL_ERROR_EXTENSION_RESTARTED;
  if (isVoiceAccessTokenError(error)) return CALL_ERROR_TOKEN_STALE;
  const text = errorText(error).trim();
  if (!text) return fallback;
  if (/twilio/i.test(text)) return fallback;
  return text;
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
