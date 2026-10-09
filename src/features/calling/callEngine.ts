/**
 * The one Vocify call: Twilio (production) or Telnyx, wherever it was dialled
 * from. The dashboard dock and the desktop island both drive and read it, so a
 * call started in one shows in the other. State transitions are `reduceCall`.
 */
import { Call, Device } from "@twilio/voice-sdk";
import { callsApi } from "@/features/calls/api";
import {
  IDLE_CALL,
  isCallUp,
  reduceCall,
  type CallEngineEvent,
  type CallEngineState,
  type DialTarget,
} from "@/lib/call-engine-state";
import {
  applyVoiceTokenRefresh,
  dispositionMessage,
  fetchVoiceTokenAfterRingback,
  isCarrierHangupError,
  isVoiceAccessTokenError,
  isVoiceSdkGeneralError,
  mapTelnyxCallState,
  startLocalRingback,
  TELNYX_RING_TIMEOUT_MS,
  telnyxHangupMessage,
  telnyxNewCallOptions,
  telnyxRtcClientOptions,
  userFacingCallError,
  voiceClientFromToken,
  watchRemoteAudio,
  type CallProductCopy,
  type VoiceClient,
} from "@/lib/dial-session";
import { CALL_STATES } from "@/lib/dial-target";
import { getDesktopBridge } from "@/lib/desktop-host";

/** Each step of a call, for the Mac app's log (read with `log stream`, category live-help, when its test switch is on). */
export function reportCallStep(step: string, details: Record<string, unknown> = {}) {
  report(step, details);
}

function report(step: string, details: Record<string, unknown> = {}) {
  getDesktopBridge()?.shell.log?.(`call:${step}`, details);
}

function errorDetails(err: unknown): Record<string, unknown> {
  const e = err as { code?: unknown; message?: unknown; name?: unknown } | null;
  return { code: e?.code ?? null, name: e?.name ?? null, message: String(e?.message ?? err ?? "") };
}

type TelnyxCall = {
  id?: string;
  hangup?: () => void;
  muteAudio?: () => void;
  unmuteAudio?: () => void;
  dtmf?: (digits: string) => void;
  localStream?: MediaStream;
  remoteStream?: MediaStream;
  sipCode?: number;
  causeCode?: number;
  cause?: string;
};

type TelnyxNotification = { type?: string; call?: TelnyxCall & { state?: string } };

/** After an unanswered hang-up, the carrier's busy / no-answer can still arrive for this long. */
const MISSED_OUTCOME_WAIT_MS = 20_000;
const DISPOSITION_POLL_MS = 1500;
/** Twilio answers a connect with a CallSid within seconds; past this the call never left this page. */
const CONNECT_TIMEOUT_MS = 20_000;
const DIGITS = /^[0-9*#]+$/;

let state: CallEngineState = IDLE_CALL;
const listeners = new Set<(s: CallEngineState) => void>();

let copy: CallProductCopy | null = null;
let client: VoiceClient = "twilio";
let device: Device | null = null;
let twilioCall: Call | null = null;
let telnyxClient: { disconnect?: () => void } | null = null;
let telnyxCall: TelnyxCall | null = null;
let stopRingbackFn: (() => void) | null = null;
let stopRemoteWatch: (() => void) | null = null;
let ringTimer: ReturnType<typeof setTimeout> | 0 = 0;
let connectTimer: ReturnType<typeof setTimeout> | 0 = 0;
let pollToken = 0;

function dispatch(event: CallEngineEvent) {
  const next = reduceCall(state, event);
  if (next === state) return;
  const wasUp = isCallUp(state);
  state = next;
  if (!wasUp && isCallUp(next)) pollDisposition();
  // The carrier has the call (or it is over): no more waiting for it to leave the page.
  if (next.callSid || !isCallUp(next)) clearTimeout(connectTimer);
  listeners.forEach((listener) => listener(state));
}

function stopRingback() {
  stopRingbackFn?.();
  stopRingbackFn = null;
  stopRemoteWatch?.();
  stopRemoteWatch = null;
}

function destroyDevice() {
  const old = device;
  device = null;
  try {
    old?.destroy();
  } catch {
    /* already gone */
  }
}

/** Ends the call locally (rep hung up, carrier hung up, or it failed). */
function hangup() {
  stopRingback();
  clearTimeout(ringTimer);
  const twilio = twilioCall;
  const telnyx = telnyxCall;
  twilioCall = null;
  telnyxCall = null;
  dispatch({ type: "ended", at: Date.now() });
  try {
    // Telnyx: hang up the call only; disconnecting the client drops SIP BYE
    // before Telnyx can tear down the parked PSTN legs.
    if (client === "telnyx") telnyx?.hangup?.();
    else twilio?.disconnect();
  } catch {
    /* already gone */
  }
}

/** Busy / no answer / canceled from our carrier webhooks, while ringing and shortly after a missed call. */
function pollDisposition() {
  const ticket = ++pollToken;
  const poll = async () => {
    if (ticket !== pollToken || state.answered) return;
    if (!isCallUp(state)) {
      const waited = state.endedAt === null ? Infinity : Date.now() - state.endedAt;
      if (state.failed || state.outcome || waited > MISSED_OUTCOME_WAIT_MS) return;
    }
    try {
      const raw = state.callSid
        ? (await callsApi.getCall(state.callSid)).callDisposition || null
        : (await callsApi.getLatestDisposition()).disposition || null;
      const message = copy ? dispositionMessage(raw, copy) : null;
      if (ticket !== pollToken) return;
      if (message) {
        dispatch({ type: "outcome", message });
        if (isCallUp(state) && !state.answered) hangup();
        return;
      }
    } catch {
      /* the WebRTC hangup or the ring timeout still ends the call */
    }
    setTimeout(poll, DISPOSITION_POLL_MS);
  };
  void poll();
}

function sdkError(err: unknown) {
  if (isVoiceAccessTokenError(err)) destroyDevice();
  dispatch({ type: "failed", message: copy ? userFacingCallError(err, copy) : null });
}

async function ensureDevice(token: string, forceNew: boolean): Promise<Device> {
  if (forceNew) destroyDevice();
  if (device) {
    device.updateToken(token);
    return device;
  }
  const next = new Device(token, { codecPreferences: [Call.Codec.Opus, Call.Codec.PCMU] });
  // Twilio's own hang-up tone (up to 3 s) stutters in the desktop app's web view; there the island shows the call ended.
  if (getDesktopBridge()) next.audio?.disconnect(false);
  // Twilio's own hang-up tone (up to 3 s) stutters in the desktop app's web view; there the island shows the call ended.
  if (getDesktopBridge()) next.audio?.disconnect(false);
  next.on("error", (err) => {
    report("device-error", errorDetails(err));
    // Before Twilio has the call, a 31005/31000 is not a hang-up: the page could not reach Twilio.
    const reachingTwilio = isCallUp(state) && !state.callSid;
    const hangupNoise =
      isCarrierHangupError(err) || isCarrierHangupError(err?.message) || isVoiceSdkGeneralError(err) || isVoiceSdkGeneralError(err?.message);
    if (hangupNoise && !reachingTwilio) return;
    sdkError(err);
    if (isCallUp(state)) hangup();
  });
  next.on("registered", () => report("device-registered"));
  next.on("tokenWillExpire", () => {
    void applyVoiceTokenRefresh({
      remint: async () => (await callsApi.createToken()).token,
      apply: (fresh) => next.updateToken(fresh),
      onFailure: () => {
        if (!isCallUp(state)) destroyDevice();
      },
    });
  });
  device = next;
  return next;
}

async function startTwilio(token: string, target: DialTarget) {
  client = "twilio";
  const connect = async (forceNew: boolean) =>
    (await ensureDevice(token, forceNew)).connect({
      params: {
        To: target.to,
        CallerId: target.callerId,
        ContactId: target.contactId || "",
        DealId: target.dealId || "",
      },
    });
  let call: Call;
  report("connect", { client: "twilio" });
  try {
    call = await connect(false);
  } catch (err) {
    if (!isVoiceAccessTokenError(err)) throw err;
    call = await connect(true);
  }
  twilioCall = call;
  report("connected", { callSid: call.parameters?.CallSid ?? null });
  call.on("warning", (name: string) => report("warning", { name }));
  const rememberSid = () => {
    const sid = call.parameters?.CallSid;
    if (sid && sid !== state.callSid) dispatch({ type: "callSid", callSid: sid });
  };
  rememberSid();
  call.on("ringing", () => {
    report("ringing");
    rememberSid();
    dispatch({ type: "ringing" });
  });
  call.on("accept", () => {
    report("accept");
    stopRingback();
    rememberSid();
    dispatch({ type: "accepted", at: Date.now() });
  });
  call.on("disconnect", hangup);
  call.on("cancel", hangup);
  call.on("error", (err) => {
    report("call-error", errorDetails(err));
    if (isCarrierHangupError(err) || isCarrierHangupError(err?.message)) {
      if (!state.answered && copy) dispatch({ type: "outcome", message: state.outcome || copy.callNoAnswer });
      hangup();
      return;
    }
    if (isVoiceSdkGeneralError(err) || isVoiceSdkGeneralError(err?.message)) {
      hangup();
      return;
    }
    sdkError(err);
    hangup();
  });
}

function telnyxRemoteElement(): HTMLAudioElement {
  const existing = document.getElementById("vocify-telnyx-remote");
  if (existing instanceof HTMLAudioElement) return existing;
  const audio = document.createElement("audio");
  audio.id = "vocify-telnyx-remote";
  audio.autoplay = true;
  document.body.appendChild(audio);
  return audio;
}

async function startTelnyx(token: string, target: DialTarget) {
  const { TelnyxRTC } = await import("@telnyx/webrtc");
  try {
    telnyxClient?.disconnect?.();
  } catch {
    /* already gone */
  }
  const rtc = new TelnyxRTC(telnyxRtcClientOptions(token));
  telnyxClient = rtc;
  client = "telnyx";
  await new Promise<void>((resolve, reject) => {
    let settled = false;
    rtc.on("telnyx.ready", () => {
      if (settled) return;
      settled = true;
      resolve();
    });
    rtc.on("telnyx.error", (err: { message?: string }) => {
      if (settled) return;
      settled = true;
      reject(new Error(err?.message || "Telnyx error"));
    });
    rtc.connect();
  });
  const remote = telnyxRemoteElement();
  const call: TelnyxCall = rtc.newCall({
    ...telnyxNewCallOptions({
      to: target.to,
      callerId: target.callerId,
      contactId: target.contactId,
      dealId: target.dealId,
    }),
    remoteElement: remote,
  });
  telnyxCall = call;
  stopRemoteWatch = watchRemoteAudio(remote, () => {
    dispatch({ type: "remoteAudio" });
    stopRingback();
  });
  ringTimer = setTimeout(() => {
    if (state.answered || !isCallUp(state)) return;
    if (copy) dispatch({ type: "outcome", message: copy.callNoAnswer });
    hangup();
  }, TELNYX_RING_TIMEOUT_MS);
  rtc.on("telnyx.notification", (notification: TelnyxNotification) => {
    if (notification?.type !== "callUpdate" || !notification.call) return;
    if (call.id && notification.call.id && notification.call.id !== call.id) return;
    const next = mapTelnyxCallState(notification.call.state);
    if (next === CALL_STATES.IDLE) {
      const ended = copy ? telnyxHangupMessage(notification.call, copy) : null;
      if (ended) dispatch({ type: "outcome", message: ended });
      hangup();
      return;
    }
    // Park answers the WebRTC leg at once; the PSTN leg is still ringing.
    if (next === CALL_STATES.ACTIVE || next === CALL_STATES.RINGING) dispatch({ type: "ringing" });
  });
}

export const callEngine = {
  getState(): CallEngineState {
    return state;
  },

  subscribe(listener: (s: CallEngineState) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  /** Places the call. Resolves with the user-facing error when it could not start. */
  async dial(target: DialTarget, callCopy: CallProductCopy): Promise<{ error: string | null }> {
    if (isCallUp(state)) return { error: null };
    copy = callCopy;
    dispatch({ type: "dial", target });
    // The SDK can wait forever (no microphone, blocked WebRTC): never leave the rep on "Calling…".
    connectTimer = setTimeout(() => {
      if (!isCallUp(state) || state.callSid) return;
      report("connect-timeout");
      dispatch({ type: "failed", message: callCopy.callStartFailed });
      hangup();
    }, CONNECT_TIMEOUT_MS);
    try {
      report("dial", { contactId: target.contactId });
      const { token: session, stop } = await fetchVoiceTokenAfterRingback(startLocalRingback, () =>
        callsApi.createToken(),
      );
      report("token", { provider: session.provider });
      stopRingbackFn = stop;
      if (voiceClientFromToken(session.provider) === "telnyx") {
        await startTelnyx(session.token, target);
      } else {
        // On the web, Twilio plays the carrier's ringback (answer_on_bridge). The desktop app's web view gets no
        // early media (nothing plays until the answer), so it keeps ringing locally until the call is answered.
        if (!getDesktopBridge()) stopRingback();
        await startTwilio(session.token, target);
      }
      return { error: null };
    } catch (err) {
      report("dial-failed", errorDetails(err));
      const message = userFacingCallError(err, callCopy);
      dispatch({ type: "failed", message });
      hangup();
      return { error: message };
    }
  },

  hangup(): void {
    if (isCallUp(state)) hangup();
  },

  setMuted(muted: boolean): void {
    if (state.phase !== "active") return;
    if (client === "telnyx") {
      if (!telnyxCall) return;
      if (muted) telnyxCall.muteAudio?.();
      else telnyxCall.unmuteAudio?.();
    } else {
      if (!twilioCall) return;
      twilioCall.mute(muted);
    }
    dispatch({ type: "muted", muted });
  },

  sendDigits(digits: string): void {
    if (state.phase !== "active" || !DIGITS.test(digits)) return;
    if (client === "telnyx") telnyxCall?.dtmf?.(digits);
    else twilioCall?.sendDigits(digits);
  },

  /** The two sides of an active call: `local` is the rep's mic, `remote` the prospect. */
  streams(): { local: MediaStream; remote: MediaStream } | null {
    if (state.phase !== "active") return null;
    const local = client === "telnyx" ? telnyxCall?.localStream : twilioCall?.getLocalStream();
    const remote = client === "telnyx" ? telnyxCall?.remoteStream : twilioCall?.getRemoteStream();
    return local && remote ? { local, remote } : null;
  },

  /**
   * The call's two sides once Twilio has attached them: right at the answer they can still be missing for a few
   * dozen milliseconds. Null if the call is no longer active or they never come.
   */
  async streamsWhenReady(timeoutMs = 5000): Promise<{ local: MediaStream; remote: MediaStream } | null> {
    const started = Date.now();
    for (;;) {
      const ready = callEngine.streams();
      if (ready || state.phase !== "active" || Date.now() - started > timeoutMs) {
        report("streams", { ready: Boolean(ready), ms: Date.now() - started });
        return ready;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  },

  /** Forgets an ended call (the island's outcome has been shown). */
  reset(): void {
    if (!isCallUp(state)) pollToken += 1;
    dispatch({ type: "reset" });
  },
};
