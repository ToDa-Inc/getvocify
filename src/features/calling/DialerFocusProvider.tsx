import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
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
  answered?: boolean;
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

type DialerFocusContextValue = {
  focus: DialerFocus | null;
  openForContact: (next: DialerFocus) => void;
  clearFocus: () => void;
  phase: DialerCallPhase;
  /** The contact on the line. Set only once the dialer actually leaves idle. */
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
  const inFlightRef = useRef(false);

  const openForContact = useCallback(
    (next: DialerFocus) => {
      setFocus(next);
      onOpenDialer();
    },
    [onOpenDialer],
  );

  const clearFocus = useCallback(() => setFocus(null), []);

  const reportLive = useCallback((live: LiveReport) => {
    setLiveElapsed(live.elapsed);
    if (live.state === CALL_STATES.IDLE) {
      inFlightRef.current = false;
      setPhase((prev) => (prev === "ended" || prev === "failed" ? prev : "idle"));
      setCallStartedAt(null);
      return;
    }
    if (!inFlightRef.current) {
      inFlightRef.current = true;
      setActiveContact(live.contact ?? null);
      setCallSid(live.callSid ?? null);
      setLastEnded(null);
    } else {
      if (live.contact) setActiveContact(live.contact);
      if (live.callSid) setCallSid(live.callSid);
    }
    setPhase(live.state === CALL_STATES.ACTIVE ? "in_call" : "dialing");
    if (live.state === CALL_STATES.ACTIVE) setCallStartedAt((prev) => prev ?? Date.now());
  }, []);

  const reportEnded = useCallback((payload: CallEndedPayload) => {
    setLastEnded(payload);
    if (payload.callSid) setCallSid(payload.callSid);
    setPhase(payload.callStatus === "failed" ? "failed" : "ended");
    setCallStartedAt(null);
  }, []);

  const clearEnded = useCallback(() => setLastEnded(null), []);

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
