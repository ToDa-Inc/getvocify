import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Device, Call } from "@twilio/voice-sdk";
import {
  MagnifyingGlass,
  Microphone,
  MicrophoneSlash,
  Phone,
  PhoneDisconnect,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { callsApi } from "@/features/calls/api";
import type { CallerId } from "@/features/calls/types";
import { crmApi } from "@/lib/api/crm";
import {
  dispositionMessage,
  isCarrierHangupError,
  isVoiceAccessTokenError,
  isVoiceSdkGeneralError,
  userFacingCallError,
  mapTelnyxCallState,
  fetchVoiceTokenAfterRingback,
  startLocalRingback,
  TELNYX_RING_TIMEOUT_MS,
  telnyxHangupMessage,
  telnyxNewCallOptions,
  telnyxRtcClientOptions,
  watchRemoteAudio,
  voiceClientFromToken,
  type VoiceClient,
} from "@/lib/dial-session";
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

type TelnyxCall = {
  id?: string;
  hangup?: () => void;
  muteAudio?: () => void;
  unmuteAudio?: () => void;
  sipCode?: number;
  causeCode?: number;
  cause?: string;
};

type TelnyxNotification = {
  type?: string;
  call?: TelnyxCall & { state?: string };
};

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
};

type Props = {
  callerIds: CallerId[];
  onLiveChange?: (live: LiveInfo) => void;
  onRequestClose?: () => void;
};

async function fetchCarrierDisposition(callSid: string | null): Promise<string | null> {
  if (callSid) {
    try {
      const call = await callsApi.getCall(callSid);
      return call.callDisposition || null;
    } catch {
      return null;
    }
  }
  const latest = await callsApi.getLatestDisposition();
  return latest.disposition || null;
}

export const DashboardDialer = ({ callerIds, onLiveChange, onRequestClose }: Props) => {
  const { t } = useLanguage();
  const callCopy = t.product;
  const verified = callerIds.filter(
    (c) => c.status === "verified" && c.source !== "twilio",
  );
  const defaultFrom =
    verified.find((c) => c.isDefault)?.phoneNumber || verified[0]?.phoneNumber || "";

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ContactHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedTarget | null>(null);
  const [from, setFrom] = useState(defaultFrom);
  const [state, setState] = useState<CallState>(CALL_STATES.IDLE);
  const [muted, setMuted] = useState(false);
  const [answeredAt, setAnsweredAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState("0:00");
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);

  const deviceRef = useRef<Device | null>(null);
  const callRef = useRef<Call | null>(null);
  const telnyxClientRef = useRef<{ disconnect?: () => void } | null>(null);
  const telnyxCallRef = useRef<TelnyxCall | null>(null);
  const stopRingbackRef = useRef<(() => void) | null>(null);
  const stopRemoteWatchRef = useRef<(() => void) | null>(null);
  const voiceClientRef = useRef<VoiceClient>("twilio");
  const hangupRef = useRef<() => void>(() => {});
  const callSidRef = useRef<string | null>(null);
  const wasAnsweredRef = useRef(false);
  const pendingMissRef = useRef(false);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const queryRef = useRef(query);
  const onLiveChangeRef = useRef(onLiveChange);
  onLiveChangeRef.current = onLiveChange;
  queryRef.current = query;

  useEffect(() => {
    if (!from && defaultFrom) setFrom(defaultFrom);
  }, [defaultFrom, from]);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!answeredAt || state !== CALL_STATES.ACTIVE) return;
    const tick = () => setElapsed(formatLiveDuration(Date.now() - answeredAt));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [answeredAt, state]);

  useEffect(() => {
    if (state !== CALL_STATES.RINGING || voiceClientRef.current !== "telnyx") {
      return;
    }
    const timer = window.setTimeout(() => {
      setOutcome("Sin respuesta");
      pendingMissRef.current = false;
      hangupRef.current();
    }, TELNYX_RING_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    const inFlight = state === CALL_STATES.RINGING || state === CALL_STATES.CONNECTING;
    const waiting = state === CALL_STATES.IDLE && pendingMissRef.current && !wasAnsweredRef.current;
    if (!inFlight && !waiting) return;
    let stopped = false;
    const started = Date.now();
    const poll = async () => {
      if (stopped) return;
      if (waiting && Date.now() - started > 20_000) {
        pendingMissRef.current = false;
        return;
      }
      try {
        const message = dispositionMessage(
          await fetchCarrierDisposition(callSidRef.current),
          callCopy,
        );
        if (message) {
          setOutcome(message);
          setError(null);
          pendingMissRef.current = false;
          if (inFlight) hangupRef.current();
          return;
        }
      } catch {
        /* WebRTC hangup or timeout will still end the call */
      }
      if (!stopped) window.setTimeout(poll, 1500);
    };
    void poll();
    return () => {
      stopped = true;
    };
  }, [state, callCopy]);

  useEffect(() => {
    onLiveChangeRef.current?.({ state, elapsed });
  }, [state, elapsed]);

  useEffect(() => {
    return () => {
      onLiveChangeRef.current?.({ state: CALL_STATES.IDLE, elapsed: "0:00" });
      try {
        if (voiceClientRef.current === "telnyx") {
          telnyxCallRef.current?.hangup?.();
        } else {
          callRef.current?.disconnect();
        }
      } catch {
        /* already gone */
      }
      try {
        telnyxClientRef.current?.disconnect?.();
      } catch {
        /* already gone */
      }
      try {
        deviceRef.current?.destroy();
      } catch {
        /* already gone */
      }
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

  const destroyDevice = () => {
    const device = deviceRef.current;
    deviceRef.current = null;
    try {
      device?.destroy();
    } catch {
      /* already gone */
    }
  };

  const ensureDevice = async (token: string, { forceNew = false } = {}) => {
    if (forceNew) destroyDevice();
    if (deviceRef.current) {
      deviceRef.current.updateToken(token);
      return deviceRef.current;
    }
    const device = new Device(token, {
      codecPreferences: [Call.Codec.Opus, Call.Codec.PCMU],
    });
    device.on("error", (err) => {
      if (
        isCarrierHangupError(err) ||
        isCarrierHangupError(err?.message) ||
        isVoiceSdkGeneralError(err) ||
        isVoiceSdkGeneralError(err?.message)
      ) {
        return;
      }
      if (isVoiceAccessTokenError(err)) destroyDevice();
      setError(userFacingCallError(err, callCopy));
      setState(CALL_STATES.IDLE);
    });
    deviceRef.current = device;
    return device;
  };

  const stopRingback = () => {
    stopRingbackRef.current?.();
    stopRingbackRef.current = null;
    stopRemoteWatchRef.current?.();
    stopRemoteWatchRef.current = null;
  };

  const hangup = () => {
    stopRingback();
    const twilioCall = callRef.current;
    const telnyxCall = telnyxCallRef.current;
    callRef.current = null;
    telnyxCallRef.current = null;
    setAnsweredAt(null);
    setMuted(false);
    setState(CALL_STATES.IDLE);
    try {
      if (voiceClientRef.current === "telnyx") {
        // Hang up the call only — disconnecting the client drops SIP BYE
        // before Telnyx can tear down the parked PSTN legs.
        telnyxCall?.hangup?.();
      } else {
        twilioCall?.disconnect();
      }
    } catch {
      /* already gone */
    }
  };
  hangupRef.current = hangup;

  const ensureTelnyxRemote = () => {
    const existing = document.getElementById("vocify-telnyx-remote");
    if (existing instanceof HTMLAudioElement) return existing;
    const audio = document.createElement("audio");
    audio.id = "vocify-telnyx-remote";
    audio.autoplay = true;
    document.body.appendChild(audio);
    return audio;
  };

  const startTelnyxCall = async (token: string, target: SelectedTarget) => {
    const { TelnyxRTC } = await import("@telnyx/webrtc");
    try {
      telnyxClientRef.current?.disconnect?.();
    } catch {
      /* already gone */
    }

    const client = new TelnyxRTC(telnyxRtcClientOptions(token));
    telnyxClientRef.current = client;
    voiceClientRef.current = "telnyx";

    await new Promise<void>((resolve, reject) => {
      let settled = false;
      client.on("telnyx.ready", () => {
        if (settled) return;
        settled = true;
        resolve();
      });
      client.on("telnyx.error", (err: { message?: string }) => {
        if (settled) return;
        settled = true;
        reject(new Error(err?.message || "Error de Telnyx"));
      });
      client.connect();
    });

    const remote = ensureTelnyxRemote();
    const call = client.newCall({
      ...telnyxNewCallOptions({
        to: target.phone,
        callerId: from,
        contactId: target.contactId,
      }),
      remoteElement: remote,
    });
    telnyxCallRef.current = call;
    stopRemoteWatchRef.current = watchRemoteAudio(remote, () => {
      stopRingback();
    });

    client.on("telnyx.notification", (notification: TelnyxNotification) => {
      if (notification?.type !== "callUpdate" || !notification.call) return;
      if (call.id && notification.call.id && notification.call.id !== call.id) {
        return;
      }
      const next = mapTelnyxCallState(notification.call.state);
      if (next === CALL_STATES.ACTIVE) {
        // Park answers the WebRTC leg immediately; PSTN is still ringing.
        setState(CALL_STATES.RINGING);
        return;
      }
      if (next === CALL_STATES.IDLE) {
        const ended = telnyxHangupMessage(notification.call, callCopy);
        if (ended) {
          setOutcome(ended);
          setError(null);
          pendingMissRef.current = false;
        }
        hangup();
        return;
      }
      setState(next);
    });
  };

  const startTwilioCall = async (token: string, target: SelectedTarget) => {
    voiceClientRef.current = "twilio";
    const connect = async (forceNew = false) => {
      const device = await ensureDevice(token, { forceNew });
      return device.connect({
        params: {
          To: target.phone,
          CallerId: from,
          ContactId: target.contactId || "",
        },
      });
    };
    let call;
    try {
      call = await connect();
    } catch (err) {
      if (!isVoiceAccessTokenError(err)) throw err;
      call = await connect(true);
    }
    callRef.current = call;
    const rememberSid = () => {
      const sid = call.parameters?.CallSid;
      if (sid) callSidRef.current = sid;
    };
    rememberSid();
    call.on("ringing", () => {
      rememberSid();
      setState(CALL_STATES.RINGING);
    });
    call.on("accept", () => {
      rememberSid();
      wasAnsweredRef.current = true;
      pendingMissRef.current = false;
      setAnsweredAt(Date.now());
      setState(CALL_STATES.ACTIVE);
    });
    call.on("disconnect", hangup);
    call.on("cancel", hangup);
    call.on("error", (err) => {
      if (isCarrierHangupError(err) || isCarrierHangupError(err?.message)) {
        if (!wasAnsweredRef.current) {
          setOutcome((prev) => prev || callCopy.callNoAnswer);
        }
        hangup();
        return;
      }
      if (isVoiceSdkGeneralError(err) || isVoiceSdkGeneralError(err?.message)) {
        hangup();
        return;
      }
      if (isVoiceAccessTokenError(err)) destroyDevice();
      setError(userFacingCallError(err, callCopy));
      pendingMissRef.current = false;
      hangup();
    });
  };

  const startCall = async (target: SelectedTarget) => {
    setError(null);
    setOutcome(null);
    if (!from) {
      toast.error("Verifica tu número antes de llamar");
      return;
    }
    callSidRef.current = null;
    wasAnsweredRef.current = false;
    pendingMissRef.current = true;
    try {
      setSelected(target);
      setState(CALL_STATES.CONNECTING);
      const { token: session, stop } = await fetchVoiceTokenAfterRingback(
        startLocalRingback,
        () => callsApi.createToken(),
      );
      stopRingbackRef.current = stop;
      const { token, provider } = session;
      if (voiceClientFromToken(provider) !== "telnyx") {
        stopRingback();
        await startTwilioCall(token, target);
        return;
      }
      await startTelnyxCall(token, target);
    } catch (err) {
      stopRingback();
      setState(CALL_STATES.IDLE);
      pendingMissRef.current = false;
      const message = userFacingCallError(err, callCopy);
      setError(message);
      if (message) toast.error(message);
    }
  };

  const callContact = (hit: ContactHit) => {
    const dest = dialTargetFromContact(hit);
    if (!dest) {
      toast.error("Este contacto no tiene teléfono");
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
    const next = !muted;
    if (voiceClientRef.current === "telnyx") {
      if (!telnyxCallRef.current) return;
      if (next) telnyxCallRef.current.muteAudio?.();
      else telnyxCallRef.current.unmuteAudio?.();
      setMuted(next);
      return;
    }
    if (!callRef.current) return;
    callRef.current.mute(next);
    setMuted(next);
  };

  if (inCall || selected) {
    const label =
      state === CALL_STATES.ACTIVE
        ? elapsed
        : state === CALL_STATES.IDLE
          ? outcome || "Listo para llamar"
          : callButtonLabel(state);

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
            <p className="mt-1 text-[11px] tabular-nums text-muted-foreground">{label}</p>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-center gap-2">
          {live ? (
            <button
              type="button"
              aria-label={muted ? "Activar micrófono" : "Silenciar"}
              aria-pressed={muted}
              onClick={toggleMute}
              className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${
                muted
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
              }`}
            >
              {muted ? (
                <MicrophoneSlash size={16} weight="light" />
              ) : (
                <Microphone size={16} weight="light" />
              )}
            </button>
          ) : null}

          <button
            type="button"
            onClick={() => {
              if (inCall) {
                hangup();
                return;
              }
              if (selected) void startCall(selected);
            }}
            disabled={!canPlace && !inCall}
            aria-label={callButtonLabel(state)}
            className={`inline-flex h-9 items-center gap-1.5 rounded-full px-4 text-[13px] transition-colors disabled:opacity-40 ${
              inCall
                ? "text-destructive hover:bg-destructive/10"
                : "bg-beige text-cream hover:bg-beige-dark"
            }`}
          >
            {inCall ? (
              <PhoneDisconnect size={15} weight="light" />
            ) : (
              <Phone size={15} weight="light" />
            )}
            {inCall ? "Colgar" : "Llamar"}
          </button>
        </div>

        {!inCall ? (
          <button
            type="button"
            onClick={() => {
              setSelected(null);
              setError(null);
              setOutcome(null);
              window.setTimeout(() => searchRef.current?.focus(), 0);
            }}
            className="mt-3 w-full text-center text-[11px] text-muted-foreground hover:text-foreground"
          >
            Buscar otro contacto
          </button>
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
              Verifica tu número
            </Link>{" "}
            para llamar
          </p>
        )}

        {error ? <p className="mt-2 text-center text-xs text-destructive">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="select-none">
      <div className="relative">
        <MagnifyingGlass
          size={14}
          weight="light"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <input
          ref={searchRef}
          type="search"
          autoComplete="off"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Nombre, email o teléfono"
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
            <Phone size={14} weight="light" className="shrink-0 text-beige" />
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
                className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-beige/10 disabled:opacity-40"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border/50 text-[9px] font-medium text-muted-foreground">
                  {contactInitials(hit.name || hit.email)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground">
                    {hit.name || hit.email || "Contacto"}
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground">
                    {[hit.jobtitle, hit.company_name, dest ? formatCallerIdDisplay(dest) : "Sin teléfono"]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </button>
            );
          })}

        {!searching && query.trim().length >= 2 && hits.length === 0 && !typedNumber ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">
            {searchError || "Ningún contacto. Prueba otro nombre."}
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
            Verifica tu número
          </Link>{" "}
          para llamar
        </p>
      )}
    </div>
  );
};
