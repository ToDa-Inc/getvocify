/**
 * The state of the one Vocify call a rep can be on, wherever it was dialled
 * from (the dashboard dock or the desktop island). The SDK wiring lives in
 * `src/features/calling/callEngine.ts`; this file is pure so it runs under node --test.
 */

export type CallPhase = "idle" | "connecting" | "ringing" | "active";

export type DialTarget = {
  /** E.164. */
  to: string;
  name: string | null;
  contactId: string | null;
  dealId: string | null;
  /** The verified number the call goes out from. */
  callerId: string;
};

export type CallEngineState = {
  phase: CallPhase;
  target: DialTarget | null;
  callSid: string | null;
  answeredAt: number | null;
  /** The prospect picked up (accept event, or their audio on a parked leg). */
  answered: boolean;
  failed: boolean;
  muted: boolean;
  /** Why an unanswered call ended (busy, no answer…), in the rep's language. */
  outcome: string | null;
  error: string | null;
  /** Set once the call ends; cleared by `reset` or the next dial. */
  endedAt: number | null;
};

export type CallEngineEvent =
  | { type: "dial"; target: DialTarget }
  | { type: "callSid"; callSid: string }
  | { type: "ringing" }
  | { type: "accepted"; at: number }
  | { type: "remoteAudio" }
  | { type: "muted"; muted: boolean }
  | { type: "outcome"; message: string }
  | { type: "failed"; message: string | null }
  | { type: "ended"; at: number }
  | { type: "reset" };

export const IDLE_CALL: CallEngineState = {
  phase: "idle",
  target: null,
  callSid: null,
  answeredAt: null,
  answered: false,
  failed: false,
  muted: false,
  outcome: null,
  error: null,
  endedAt: null,
};

export function isCallUp(state: CallEngineState): boolean {
  return state.phase !== "idle";
}

export function isCallEnded(state: CallEngineState): boolean {
  return state.phase === "idle" && state.endedAt !== null;
}

export function reduceCall(state: CallEngineState, event: CallEngineEvent): CallEngineState {
  switch (event.type) {
    case "dial":
      if (isCallUp(state)) return state;
      return { ...IDLE_CALL, phase: "connecting", target: event.target };
    case "callSid":
      return isCallUp(state) ? { ...state, callSid: event.callSid } : state;
    case "ringing":
      return isCallUp(state) && state.phase !== "active" ? { ...state, phase: "ringing" } : state;
    case "accepted":
      if (!isCallUp(state)) return state;
      return { ...state, phase: "active", answered: true, answeredAt: event.at, outcome: null };
    case "remoteAudio":
      return isCallUp(state) ? { ...state, answered: true } : state;
    case "muted":
      return state.phase === "active" ? { ...state, muted: event.muted } : state;
    case "outcome":
      if (state.answered || (!isCallUp(state) && !isCallEnded(state))) return state;
      return { ...state, outcome: event.message, error: null };
    case "failed":
      return { ...state, failed: true, error: event.message };
    case "ended":
      if (!isCallUp(state)) return state;
      return { ...state, phase: "idle", muted: false, endedAt: event.at };
    case "reset":
      return isCallUp(state) ? state : IDLE_CALL;
  }
}
