import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { Mic, MicOff, PhoneOff, Search } from "lucide-react";
import { AnimIcon } from "@/components/ui/anim-icon";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { toast } from "sonner";
import type { CallerId } from "@/features/calls/types";
import { callEngine } from "@/features/calling/callEngine";
import { crmApi } from "@/lib/api/crm";
import { useLanguage } from "@/lib/i18n";
import { ROUTES } from "@/shared/lib/constants";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import {
  CALL_STATES,
  callButtonLabel,
  canMute,
  contactInitials,
  dialTargetFromContact,
  formatCallerIdDisplay,
  formatLiveDuration,
  normalizeDialTarget,
  type CallState,
} from "@/lib/dial-target";
import type { CallEndedPayload, DialerFocus } from "@/features/calling/DialerFocusProvider";
import { ContactBrief } from "@/components/dashboard/memos/ContactBrief";
import { useRecordingBusy } from "@/features/desktop/DesktopMeetingProvider";
import { useAuth } from "@/features/auth";

type ContactHit = {
  contact_id: string;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  jobtitle?: string | null;
  company_name?: string | null;
};

type SelectedTarget = {
  contactId?: string | null;
  name: string;
  phone: string;
};

type LiveInfo = {
  state: CallState;
  elapsed: string;
  contact?: DialerFocus | null;
  callSid?: string | null;
};

type Props = {
  callerIds: CallerId[];
  onLiveChange?: (live: LiveInfo) => void;
  onRequestClose?: () => void;
  focusContact?: DialerFocus | null;
  onFocusHandled?: () => void;
  compact?: boolean;
  /** Off when the rep home's contact panel already shows the brief. */
  showBrief?: boolean;
  onCallEnded?: (payload: CallEndedPayload) => void;
};

export const DashboardDialer = ({
  callerIds,
  onLiveChange,
  onRequestClose,
  focusContact = null,
  onFocusHandled,
  compact = false,
  showBrief = true,
  onCallEnded,
}: Props) => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const callCopy = t.product;
  const verified = callerIds.filter(
    (c) => c.status === "verified" && c.source !== "twilio" && !c.callBlocked,
  );
  const defaultFrom =
    verified.find((c) => c.isDefault)?.phoneNumber || verified[0]?.phoneNumber || "";

  // The call lives in callEngine, so one dialled from the desktop island shows here too.
  const call = useSyncExternalStore(callEngine.subscribe, callEngine.getState);
  const state: CallState = call.phase;
  const { muted, answeredAt, error, outcome } = call;
  // Desktop app: a meeting being recorded holds the mic and the island; a call waits for it to end.
  const recordingBusy = useRecordingBusy();

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ContactHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [picked, setPicked] = useState<SelectedTarget | null>(null);
  const [from, setFrom] = useState(defaultFrom);
  const [elapsed, setElapsed] = useState("0:00");

  const searchRef = useRef<HTMLInputElement | null>(null);
  const queryRef = useRef(query);
  const onLiveChangeRef = useRef(onLiveChange);
  const onCallEndedRef = useRef(onCallEnded);
  const wasInCallRef = useRef(false);
  const endedReportedRef = useRef(false);
  onLiveChangeRef.current = onLiveChange;
  onCallEndedRef.current = onCallEnded;
  queryRef.current = query;

  const selected: SelectedTarget | null =
    picked ??
    (call.target
      ? {
          contactId: call.target.contactId,
          name: call.target.name || formatCallerIdDisplay(call.target.to),
          phone: call.target.to,
        }
      : null);

  useEffect(() => {
    if (!from && defaultFrom) setFrom(defaultFrom);
  }, [defaultFrom, from]);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!focusContact?.contactId || state !== CALL_STATES.IDLE) return;
    let cancelled = false;
    void (async () => {
      try {
        const results = await crmApi.searchContacts(focusContact.contactId);
        if (cancelled) return;
        const hit =
          results.find((row: ContactHit) => row.contact_id === focusContact.contactId) ?? results[0];
        if (!hit) return;
        const dest = dialTargetFromContact(hit);
        if (!dest) return;
        const name = hit.name || focusContact.name || hit.contact_id;
        setPicked({ contactId: hit.contact_id, name, phone: dest });
        setQuery(name);
        setHits(results);
      } finally {
        if (!cancelled) onFocusHandled?.();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [focusContact?.contactId, focusContact?.name, onFocusHandled, state]);

  useEffect(() => {
    if (!answeredAt || state !== CALL_STATES.ACTIVE) return;
    const tick = () => setElapsed(formatLiveDuration(Date.now() - answeredAt));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [answeredAt, state]);

  useEffect(() => {
    const contact =
      selected?.contactId != null
        ? { contactId: selected.contactId, name: selected.name }
        : focusContact;
    onLiveChangeRef.current?.({ state, elapsed, contact, callSid: call.callSid });
    if (state !== CALL_STATES.IDLE) {
      wasInCallRef.current = true;
      endedReportedRef.current = false;
      return;
    }
    if (!wasInCallRef.current || endedReportedRef.current) return;
    wasInCallRef.current = false;
    endedReportedRef.current = true;
    // Memo and screening only exist once the recording is processed; the home polls for them.
    const failed = call.failed || !call.answered;
    onCallEndedRef.current?.({
      callSid: call.callSid,
      answered: call.answered,
      callStatus: failed ? "failed" : undefined,
    });
  }, [state, elapsed, selected?.contactId, selected?.name, focusContact, call.callSid, call.failed, call.answered]);

  useEffect(() => {
    return () => {
      onLiveChangeRef.current?.({ state: CALL_STATES.IDLE, elapsed: "0:00" });
    };
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (state !== CALL_STATES.IDLE || q.length < 2) {
      if (q.length < 2) {
        setHits([]);
        setSearchError(null);
      }
      setSearching(false);
      return;
    }
    setSearching(true);
    setSearchError(null);
    const timer = window.setTimeout(async () => {
      try {
        const results = await crmApi.searchContacts(q);
        if (queryRef.current.trim() !== q) return;
        setHits(Array.isArray(results) ? results : []);
      } catch {
        if (queryRef.current.trim() !== q) return;
        setHits([]);
        setSearchError(callCopy.callHubSpotSearchFailed);
      } finally {
        if (queryRef.current.trim() === q) setSearching(false);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query, state, callCopy]);

  const hangup = () => callEngine.hangup();

  const startCall = async (target: SelectedTarget) => {
    if (!from) {
      toast.error(callCopy.dialVerifyBeforeCall);
      return;
    }
    if (recordingBusy) {
      toast.error("Stop the recording before calling.");
      return;
    }
    setPicked(target);
    const { error: failed } = await callEngine.dial(
      { to: target.phone, name: target.name, contactId: target.contactId ?? null, dealId: null, callerId: from },
      callCopy,
    );
    if (failed) toast.error(failed);
  };

  const callContact = (hit: ContactHit) => {
    const dest = dialTargetFromContact(hit);
    if (!dest) {
      toast.error(callCopy.dialContactNoPhone);
      return;
    }
    void startCall({
      contactId: hit.contact_id,
      name: hit.name || hit.email || formatCallerIdDisplay(dest),
      phone: dest,
    });
  };

  const callTypedNumber = (dest: string) => {
    void startCall({
      name: formatCallerIdDisplay(dest),
      phone: dest,
    });
  };

  const inCall = state !== CALL_STATES.IDLE;
  const live = state === CALL_STATES.ACTIVE;
  const typedNumber = normalizeDialTarget(query);
  const typedAlreadyListed =
    Boolean(typedNumber) &&
    hits.some((hit) => dialTargetFromContact(hit) === typedNumber);
  const canPlace = verified.length > 0;

  const toggleMute = () => {
    if (!canMute(state)) return;
    callEngine.setMuted(!muted);
  };

  if (inCall || selected) {
    const label =
      state === CALL_STATES.ACTIVE
        ? elapsed
        : state === CALL_STATES.IDLE
          ? outcome || callCopy.dialReadyToCall
          : callButtonLabel(state);
    // Rings until they pick up, so the rep sees the call is alive without reading the label.
    const ringing = state === CALL_STATES.RINGING || state === CALL_STATES.CONNECTING;
    const ring = ringing ? <AnimIcon name="phone" size={11} stroke={1.5} state="ringing" /> : null;

    if (compact && inCall) {
      return (
        <div className="select-none">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/50 text-[10px] font-medium text-muted-foreground">
              {contactInitials(selected?.name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-foreground">{selected?.name}</p>
              <p className="mt-0.5 flex items-center gap-1 text-[11px] tabular-nums text-beige">{ring}{label}</p>
            </div>
            <div className="flex items-center gap-2">
              {state === CALL_STATES.ACTIVE ? (
                <IconAction label={muted ? callCopy.dialUnmuteMic : callCopy.dialMuteMic} pressed={muted} onClick={toggleMute}>
                  {muted ? (
                    <MicOff size={15} strokeWidth={1.5} />
                  ) : (
                    <Mic size={15} strokeWidth={1.5} />
                  )}
                </IconAction>
              ) : null}
              <Button
                type="button"
                variant="dangerGhost"
                size="sm"
                onClick={() => hangup()}
                className="gap-1.5"
              >
                <PhoneOff size={15} strokeWidth={1.5} />
                {callCopy.panel_hang_up}
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="select-none">
        <div className="flex items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/50 text-[10px] font-medium text-muted-foreground">
            {contactInitials(selected?.name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-foreground">
              {selected?.name}
            </p>
            <p className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">
              {selected ? formatCallerIdDisplay(selected.phone) : ""}
            </p>
            <p className="mt-1 flex items-center gap-1 text-[11px] tabular-nums text-muted-foreground">{ring}{label}</p>
          </div>
        </div>

        {showBrief && !compact && user?.company?.briefV2 && selected?.contactId ? (
          <div className="mt-3">
            <ContactBrief contactId={selected.contactId} compact />
          </div>
        ) : null}

        <div className="mt-4 flex items-center justify-center gap-2">
          {live ? (
            <IconAction label={muted ? callCopy.dialUnmuteMic : callCopy.dialMuteMic} pressed={muted} onClick={toggleMute}>
              {muted ? (
                <MicOff size={16} strokeWidth={1.5} />
              ) : (
                <Mic size={16} strokeWidth={1.5} />
              )}
            </IconAction>
          ) : null}

          <Button
            type="button"
            size="sm"
            onClick={() => {
              if (inCall) {
                hangup();
                return;
              }
              if (selected) void startCall(selected);
            }}
            disabled={!canPlace && !inCall}
            aria-label={callButtonLabel(state)}
            variant={inCall ? "dangerGhost" : "default"}
            className="gap-1.5"
          >
            {inCall ? (
              <PhoneOff size={15} strokeWidth={1.5} />
            ) : (
              <AnimIcon name="phone" size={15} stroke={1.25} />
            )}
            {inCall ? "Colgar" : "Llamar"}
          </Button>
        </div>

        {!inCall ? (
          <Button
            type="button"
            variant="quiet"
            size="text"
            onClick={() => {
              setPicked(null);
              callEngine.reset();
              window.setTimeout(() => searchRef.current?.focus(), 0);
            }}
            className="mt-3 w-full"
          >
            Buscar otro contacto
          </Button>
        ) : null}

        {from ? (
          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            Sale como {formatCallerIdDisplay(from)}
          </p>
        ) : (
          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            <Link
              to={ROUTES.CALLING}
              onClick={() => onRequestClose?.()}
              className="text-beige hover:underline"
            >
              {callCopy.dialVerifyNumber}
            </Link>{" "}
            {callCopy.dialToCallHint}
          </p>
        )}

        {error ? <p className="mt-2 text-center text-xs text-destructive">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="select-none">
      <div className="relative">
        <Search
          size={14}
          strokeWidth={1.5}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <input
          ref={searchRef}
          type="search"
          autoComplete="off"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={callCopy.dialSearchPlaceholder}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            const first = hits.find((hit) => dialTargetFromContact(hit));
            if (first) {
              callContact(first);
              return;
            }
            if (typedNumber) callTypedNumber(typedNumber);
          }}
          className="w-full rounded-xl border border-border/50 bg-card py-2 pl-9 pr-3 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-beige/40"
        />
      </div>

      <div className="mt-2 max-h-56 overflow-y-auto">
        {typedNumber && !typedAlreadyListed ? (
          <button
            type="button"
            disabled={!canPlace}
            onClick={() => callTypedNumber(typedNumber)}
            className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-beige/10 disabled:opacity-40"
          >
            <AnimIcon name="phone" size={14} stroke={1.25} className="text-beige" />
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium text-foreground">
                Llamar a {formatCallerIdDisplay(typedNumber)}
              </span>
              <span className="block text-[11px] text-muted-foreground">Número escrito</span>
            </span>
          </button>
        ) : null}

        {searching ? (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
            <VocifySpinner size={12} />
            Buscando…
          </div>
        ) : null}

        {!searching &&
          [...hits]
            .sort((a, b) => {
              const aOk = dialTargetFromContact(a) ? 0 : 1;
              const bOk = dialTargetFromContact(b) ? 0 : 1;
              return aOk - bOk;
            })
            .map((hit) => {
            const dest = dialTargetFromContact(hit);
            return (
              <button
                key={hit.contact_id}
                type="button"
                disabled={!canPlace || !dest}
                onClick={() => callContact(hit)}
                className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-secondary/60 disabled:opacity-40"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border/50 text-[9px] font-medium text-muted-foreground">
                  {contactInitials(hit.name || hit.email)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground">
                    {hit.name || hit.email || "Contacto"}
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground">
                    {[hit.jobtitle, hit.company_name, dest ? formatCallerIdDisplay(dest) : callCopy.dialNoPhone]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </button>
            );
          })}

        {!searching && query.trim().length >= 2 && hits.length === 0 && !typedNumber ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">
            {searchError || callCopy.dialNoContactsTryAnother}
          </p>
        ) : null}

        {query.trim().length < 2 ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">
            Busca un contacto de HubSpot y llama.
          </p>
        ) : null}
      </div>

      {from ? (
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          Sale como {formatCallerIdDisplay(from)}
        </p>
      ) : (
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          <Link
            to={ROUTES.CALLING}
            onClick={() => onRequestClose?.()}
            className="text-beige hover:underline"
          >
            {callCopy.dialVerifyNumber}
          </Link>{" "}
          {callCopy.dialToCallHint}
        </p>
      )}
    </div>
  );
};
