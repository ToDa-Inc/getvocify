import { useEffect, useRef, useState } from "react";
import { Device, Call } from "@twilio/voice-sdk";
import { Delete, Mic, MicOff, Phone, PhoneOff } from "lucide-react";
import { toast } from "sonner";
import { callsApi } from "@/features/calls/api";
import type { CallerId } from "@/features/calls/types";
import {
  CALL_STATES,
  callButtonLabel,
  canMute,
  canSendDigits,
  formatCallerIdDisplay,
  formatLiveDuration,
  normalizeDialTarget,
  type CallState,
} from "@/lib/dial-target";

const KEYS: { digit: string; letters: string }[] = [
  { digit: "1", letters: "" },
  { digit: "2", letters: "ABC" },
  { digit: "3", letters: "DEF" },
  { digit: "4", letters: "GHI" },
  { digit: "5", letters: "JKL" },
  { digit: "6", letters: "MNO" },
  { digit: "7", letters: "PQRS" },
  { digit: "8", letters: "TUV" },
  { digit: "9", letters: "WXYZ" },
  { digit: "*", letters: "" },
  { digit: "0", letters: "+" },
  { digit: "#", letters: "" },
];

type Props = {
  callerIds: CallerId[];
};

export const DashboardDialer = ({ callerIds }: Props) => {
  const verified = callerIds.filter(
    (c) => c.status === "verified" && c.source !== "twilio",
  );
  const defaultFrom =
    verified.find((c) => c.isDefault)?.phoneNumber || verified[0]?.phoneNumber || "";

  const [to, setTo] = useState("");
  const [from, setFrom] = useState(defaultFrom);
  const [state, setState] = useState<CallState>(CALL_STATES.IDLE);
  const [muted, setMuted] = useState(false);
  const [answeredAt, setAnsweredAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState("0:00");
  const [error, setError] = useState<string | null>(null);

  const deviceRef = useRef<Device | null>(null);
  const callRef = useRef<Call | null>(null);

  useEffect(() => {
    if (!from && defaultFrom) setFrom(defaultFrom);
  }, [defaultFrom, from]);

  useEffect(() => {
    if (!answeredAt || state !== CALL_STATES.ACTIVE) return;
    const tick = () => setElapsed(formatLiveDuration(Date.now() - answeredAt));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [answeredAt, state]);

  useEffect(() => {
    return () => {
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

  const startCall = async () => {
    setError(null);
    const dest = normalizeDialTarget(to);
    if (!dest) {
      toast.error("Introduce un número válido");
      return;
    }
    if (!from) {
      toast.error("Verifica tu número antes de llamar");
      return;
    }
    try {
      setState(CALL_STATES.CONNECTING);
      const { token } = await callsApi.createToken();
      const device = await ensureDevice(token);
      const call = await device.connect({
        params: { To: dest, CallerId: from },
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

  const inCall = state !== CALL_STATES.IDLE;
  const live = state === CALL_STATES.ACTIVE;

  const pressKey = (digit: string) => {
    if (live && canSendDigits(state) && callRef.current) {
      callRef.current.sendDigits(digit);
      return;
    }
    if (!inCall) {
      setTo((prev) => `${prev}${digit}`);
    }
  };

  const backspace = () => {
    if (inCall) return;
    setTo((prev) => prev.slice(0, -1));
  };

  const onAction = () => {
    if (state === CALL_STATES.IDLE) {
      void startCall();
      return;
    }
    hangup();
  };

  const toggleMute = () => {
    if (!canMute(state) || !callRef.current) return;
    const next = !muted;
    callRef.current.mute(next);
    setMuted(next);
  };

  const statusLabel =
    state === CALL_STATES.ACTIVE
      ? elapsed
      : state === CALL_STATES.IDLE
        ? " "
        : callButtonLabel(state);

  return (
    <div className="mx-auto w-full max-w-[240px] select-none">
      <div className="relative mb-0.5 min-h-[2.75rem] text-center">
        <input
          id="dialer-to"
          type="tel"
          inputMode="tel"
          autoComplete="off"
          value={to}
          onChange={(e) => !inCall && setTo(e.target.value)}
          placeholder="Número"
          disabled={inCall}
          className="w-full bg-transparent text-center text-[1.2rem] font-medium tabular-nums tracking-tight text-foreground outline-none placeholder:text-muted-foreground/50 disabled:opacity-80"
        />
        <p className="h-3.5 text-[11px] text-muted-foreground">{statusLabel}</p>
        {to && !inCall ? (
          <button
            type="button"
            aria-label="Borrar"
            onClick={backspace}
            className="absolute right-0 top-1 rounded-full p-1 text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
          >
            <Delete className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="grid grid-cols-3 gap-x-2.5 gap-y-1.5 py-0.5">
        {KEYS.map(({ digit, letters }) => (
          <button
            key={digit}
            type="button"
            onClick={() => pressKey(digit)}
            className="flex h-11 flex-col items-center justify-center rounded-full bg-secondary/70 text-foreground transition-colors hover:bg-secondary active:scale-[0.96]"
          >
            <span className="text-[1.15rem] font-medium leading-none">{digit}</span>
            {letters ? (
              <span className="mt-0.5 text-[8px] font-medium tracking-[0.14em] text-muted-foreground">
                {letters}
              </span>
            ) : (
              <span className="mt-0.5 h-[10px]" />
            )}
          </button>
        ))}
      </div>

      <div className="mt-2.5 flex items-center justify-center gap-4">
        {live ? (
          <button
            type="button"
            aria-label={muted ? "Activar micrófono" : "Silenciar"}
            aria-pressed={muted}
            onClick={toggleMute}
            className={`flex h-10 w-11 items-center justify-center rounded-full transition-colors ${
              muted
                ? "bg-foreground text-background"
                : "bg-secondary text-foreground hover:bg-secondary/80"
            }`}
          >
            {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
        ) : (
          <span className="h-10 w-11" />
        )}

        <button
          type="button"
          onClick={onAction}
          disabled={verified.length === 0 && state === CALL_STATES.IDLE}
          aria-label={callButtonLabel(state)}
          className={`flex h-12 w-12 items-center justify-center rounded-full text-cream shadow-sm transition-transform active:scale-95 disabled:opacity-40 ${
            inCall ? "bg-destructive hover:bg-destructive/90" : "bg-beige hover:bg-beige-dark"
          }`}
        >
          {inCall ? <PhoneOff className="h-5 w-5" /> : <Phone className="h-5 w-5" />}
        </button>
        <span className="h-11 w-11" />
      </div>

      {from ? (
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          Caller ID {formatCallerIdDisplay(from)}
        </p>
      ) : (
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          Verifica tu número abajo para llamar
        </p>
      )}

      {error ? <p className="mt-2 text-center text-xs text-destructive">{error}</p> : null}
    </div>
  );
};
