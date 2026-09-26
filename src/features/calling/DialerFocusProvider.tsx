import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CALL_STATES, type CallState } from "@/lib/dial-target";
import { dialerReticleStore } from "@/lib/dialer-reticle-store";

export type DialerFocus = {
  contactId: string;
  name?: string | null;
};

export type DialerCallPhase = "idle" | "dialing" | "in_call" | "ended" | "failed";

export type CallEndedPayload = {
  callSid: string | null;
  memoId?: string | null;
  screeningOutcome?: string | null;
  callStatus?: "failed";
  durationSeconds?: number | null;
};

type LiveReport = {
  state: CallState;
  elapsed: string;
  contact?: DialerFocus | null;
  callSid?: string | null;
};

function phaseFromCallState(state: CallState, failed: boolean): DialerCallPhase {
  if (failed) return "failed";
  if (state === CALL_STATES.IDLE) return "idle";
  if (state === CALL_STATES.ACTIVE) return "in_call";
  return "dialing";
}

type DialerFocusContextValue = {
  focus: DialerFocus | null;
  openForContact: (next: DialerFocus) => void;
  clearFocus: () => void;
  phase: DialerCallPhase;
  activeContact: DialerFocus | null;
  callStartedAt: number | null;
  callSid: string | null;
  liveElapsed: string;
  lastEnded: CallEndedPayload | null;
  reportLive: (live: LiveReport) => void;
  reportEnded: (payload: CallEndedPayload) => void;
  clearEnded: () => void;
};

const DialerFocusContext = createContext<DialerFocusContextValue | null>(null);

export function DialerFocusProvider({
  children,
  onOpenDialer,
}: {
  children: ReactNode;
  onOpenDialer: () => void;
}) {
  const [focus, setFocus] = useState<DialerFocus | null>(null);
  const [phase, setPhase] = useState<DialerCallPhase>("idle");
  const [activeContact, setActiveContact] = useState<DialerFocus | null>(null);
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callSid, setCallSid] = useState<string | null>(null);
  const [liveElapsed, setLiveElapsed] = useState("0:00");
  const [lastEnded, setLastEnded] = useState<CallEndedPayload | null>(null);
  const [failed, setFailed] = useState(false);

  const openForContact = useCallback(
    (next: DialerFocus) => {
      setFocus(next);
      setActiveContact(next);
      setLastEnded(null);
      onOpenDialer();
    },
    [onOpenDialer],
  );

  const clearFocus = useCallback(() => setFocus(null), []);

  const reportLive = useCallback((live: LiveReport) => {
    setPhase((prev) => {
      const nextFailed = failed && live.state === CALL_STATES.IDLE ? failed : false;
      return phaseFromCallState(live.state, nextFailed);
    });
    setLiveElapsed(live.elapsed);
    if (live.contact) setActiveContact(live.contact);
    if (live.callSid) setCallSid(live.callSid);
    if (live.state === CALL_STATES.ACTIVE) {
      setCallStartedAt((prev) => prev ?? Date.now());
    }
    if (live.state === CALL_STATES.IDLE) {
      setCallStartedAt(null);
    }
    if (live.state !== CALL_STATES.IDLE) {
      setFailed(false);
      setLastEnded(null);
    }
  }, [failed]);

  const reportEnded = useCallback((payload: CallEndedPayload) => {
    setLastEnded(payload);
    setCallSid(payload.callSid);
    setPhase(payload.callStatus === "failed" ? "failed" : "ended");
    setFailed(payload.callStatus === "failed");
    setCallStartedAt(null);
  }, []);

  const clearEnded = useCallback(() => {
    setLastEnded(null);
    setPhase("idle");
    setFailed(false);
    setActiveContact(null);
    setCallSid(null);
  }, []);

  useEffect(() => {
    dialerReticleStore.setState({
      phase,
      contactId: activeContact?.contactId ?? null,
      contactName: activeContact?.name ?? null,
      callSid,
      elapsed: liveElapsed,
    });
  }, [phase, activeContact, callSid, liveElapsed]);

  const value = useMemo(
    () => ({
      focus,
      openForContact,
      clearFocus,
      phase,
      activeContact,
      callStartedAt,
      callSid,
      liveElapsed,
      lastEnded,
      reportLive,
      reportEnded,
      clearEnded,
    }),
    [
      focus,
      openForContact,
      clearFocus,
      phase,
      activeContact,
      callStartedAt,
      callSid,
      liveElapsed,
      lastEnded,
      reportLive,
      reportEnded,
      clearEnded,
    ],
  );

  return <DialerFocusContext.Provider value={value}>{children}</DialerFocusContext.Provider>;
}

export function useDialerFocus(): DialerFocusContextValue {
  const ctx = useContext(DialerFocusContext);
  if (!ctx) {
    throw new Error("useDialerFocus must be used within DialerFocusProvider");
  }
  return ctx;
}

export function useOptionalDialerFocus(): DialerFocusContextValue | null {
  return useContext(DialerFocusContext);
}
