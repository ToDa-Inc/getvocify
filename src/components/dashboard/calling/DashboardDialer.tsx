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

export const DashboardDialer = ({ callerIds, onLiveChange, onRequestClose }: Props) => {
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

  const deviceRef = useRef<Device | null>(null);
  const callRef = useRef<Call | null>(null);
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
    onLiveChangeRef.current?.({ state, elapsed });
  }, [state, elapsed]);

  useEffect(() => {
    return () => {
      onLiveChangeRef.current?.({ state: CALL_STATES.IDLE, elapsed: "0:00" });
      try {
        callRef.current?.disconnect();
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
        setSearchError("No se pudo buscar en HubSpot");
      } finally {
        if (queryRef.current.trim() === q) setSearching(false);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query, state]);

  const ensureDevice = async (token: string) => {
    if (deviceRef.current) {
      deviceRef.current.updateToken(token);
      return deviceRef.current;
    }
    const device = new Device(token, {
      codecPreferences: [Call.Codec.Opus, Call.Codec.PCMU],
    });
    device.on("error", (err) => {
      setError(err?.message || "Error de Twilio");
      setState(CALL_STATES.IDLE);
    });
    deviceRef.current = device;
    return device;
  };

  const hangup = () => {
    const call = callRef.current;
    callRef.current = null;
    setAnsweredAt(null);
    setMuted(false);
    setState(CALL_STATES.IDLE);
    try {
      call?.disconnect();
    } catch {
      /* already gone */
    }
  };

  const startCall = async (target: SelectedTarget) => {
    setError(null);
    if (!from) {
      toast.error("Verifica tu número antes de llamar");
      return;
    }
    try {
      setSelected(target);
      setState(CALL_STATES.CONNECTING);
      const { token } = await callsApi.createToken();
      const device = await ensureDevice(token);
      const call = await device.connect({
        params: {
          To: target.phone,
          CallerId: from,
          ContactId: target.contactId || "",
        },
      });
      callRef.current = call;
      call.on("ringing", () => setState(CALL_STATES.RINGING));
      call.on("accept", () => {
        setAnsweredAt(Date.now());
        setState(CALL_STATES.ACTIVE);
      });
      call.on("disconnect", hangup);
      call.on("cancel", hangup);
      call.on("error", (err) => {
        setError(err?.message || "Error de llamada");
        hangup();
      });
    } catch (err) {
      setState(CALL_STATES.IDLE);
      const message = err instanceof Error ? err.message : "No se pudo iniciar la llamada";
      setError(message);
      toast.error(message);
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
    if (!canMute(state) || !callRef.current) return;
    const next = !muted;
    callRef.current.mute(next);
    setMuted(next);
  };

  if (inCall || selected) {
    const label =
      state === CALL_STATES.ACTIVE
        ? elapsed
        : state === CALL_STATES.IDLE
          ? "Listo para llamar"
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
