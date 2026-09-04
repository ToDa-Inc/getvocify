import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useAuth } from "@/features/auth";
import { callsApi } from "@/features/calls/api";
import type { CallerId, CallingConfig } from "@/features/calls/types";
import { ApiError } from "@/shared/lib/api-client";
import { callerIdFormVisible } from "@/lib/dial-target";

const POLL_MS = 3000;
const POLL_MAX_MS = 120_000;

export const CallerIdSettings = () => {
  const { user } = useAuth();
  const [config, setConfig] = useState<CallingConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [number, setNumber] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [verificationCode, setVerificationCode] = useState<string | null>(null);
  const [pollExpired, setPollExpired] = useState(false);
  const pollUntilRef = useRef<number | null>(null);
  const pollIdRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const next = await callsApi.getConfig();
    setConfig(next);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await callsApi.getConfig();
        if (!cancelled) setConfig(next);
      } catch (error) {
        console.error("Failed to load calling config", error);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const stopPoll = () => {
    if (pollIdRef.current != null) {
      window.clearInterval(pollIdRef.current);
      pollIdRef.current = null;
    }
    pollUntilRef.current = null;
  };

  useEffect(() => {
    return () => stopPoll();
  }, []);

  const ids = (config?.callerIds || []).filter((c) => c.source !== "twilio");
  const hasPending = ids.some((c) => c.status === "pending");

  useEffect(() => {
    if (!hasPending || !config?.enabled) {
      stopPoll();
      return;
    }
    if (pollIdRef.current != null) return;
    pollUntilRef.current = Date.now() + POLL_MAX_MS;
    pollIdRef.current = window.setInterval(async () => {
      if (pollUntilRef.current && Date.now() > pollUntilRef.current) {
        stopPoll();
        setPollExpired(true);
        return;
      }
      try {
        const next = await load();
        if (!next.callerIds.some((c) => c.status === "pending")) {
          stopPoll();
          setVerificationCode(null);
        }
      } catch {
        /* keep polling */
      }
    }, POLL_MS);
    return () => stopPoll();
  }, [hasPending, config?.enabled, load]);

  const whatsappPhone = user?.phone || "";
  const whatsappUnused =
    Boolean(whatsappPhone) && !ids.some((c) => c.phoneNumber === whatsappPhone);

  const handleVerify = async () => {
    const raw = number.trim();
    if (!raw) return;
    try {
      setIsSaving(true);
      setPollExpired(false);
      const result = await callsApi.addCallerId(raw);
      if (result.alreadyVerified) {
        setVerificationCode(null);
        toast.success("Este número ya está verificado");
      } else if (result.verificationCode) {
        setVerificationCode(result.verificationCode);
      } else {
        setVerificationCode(null);
      }
      setNumber("");
      await load();
    } catch (error) {
      const detail =
        error instanceof ApiError &&
        error.data &&
        typeof error.data === "object" &&
        "detail" in error.data &&
        typeof (error.data as { detail: unknown }).detail === "string"
          ? (error.data as { detail: string }).detail
          : null;
      toast.error(detail || "No se pudo iniciar la verificación");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDefault = async (phoneNumber: string) => {
    try {
      const result = await callsApi.setDefaultCallerId(phoneNumber);
      setConfig((prev) =>
        prev ? { ...prev, callerIds: result.callerIds } : prev,
      );
    } catch {
      toast.error("No se pudo marcar como predeterminado");
    }
  };

  const handleDelete = async (row: CallerId) => {
    if (!window.confirm(`¿Eliminar ${row.phoneNumber}?`)) return;
    try {
      await callsApi.deleteCallerId(row.phoneNumber);
      await load();
    } catch {
      toast.error("No se pudo eliminar el número");
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-beige" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Caller ID</h3>
        <p className="text-xs text-muted-foreground mt-1">
          El número que verán tus prospectos. Twilio te llamará, en
          inglés, y teclearás un código.
        </p>
      </div>

      {!config?.enabled && (
        <p className="text-sm text-muted-foreground">
          Las llamadas no están configuradas en este entorno.
        </p>
      )}

      {config?.enabled && config.hubspotLogging === false && (
        <p className="text-xs text-muted-foreground">
          Las llamadas se grabarán en Vocify, pero no se registrarán en HubSpot
          hasta que HUBSPOT_APP_ID esté configurado.
        </p>
      )}

      {ids.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Verifica tu número una vez. Twilio te llamará, en inglés, desde un
          número de Estados Unidos, y teclearás un código.
        </p>
      ) : (
        <ul className="space-y-3">
          {ids.map((row) => (
            <li
              key={row.phoneNumber}
              className="flex flex-wrap items-center gap-2 rounded-xl border border-border/40 px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{row.phoneNumber}</p>
                {row.label ? (
                  <p className="text-xs text-muted-foreground">{row.label}</p>
                ) : null}
              </div>
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {row.status}
              </span>
              {row.status === "verified" &&
              !row.isDefault &&
              ids.filter((c) => c.status === "verified").length > 1 ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="h-8 rounded-full px-3 text-[10px]"
                  onClick={() => handleDefault(row.phoneNumber)}
                >
                  Hacer predeterminado
                </Button>
              ) : null}
              {row.source !== "twilio" ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="h-8 rounded-full px-3 text-[10px]"
                  onClick={() => handleDelete(row)}
                >
                  Eliminar
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {callerIdFormVisible({ isLoading, enabled: config?.enabled }) && (
        <div className="space-y-3">
          {whatsappUnused && (
            <button
              type="button"
              className="text-xs text-beige underline"
              onClick={() => setNumber(whatsappPhone)}
            >
              Usar {whatsappPhone} (tu número de WhatsApp)
            </button>
          )}
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              placeholder="+34 600 111 222"
              className="rounded-full h-11"
            />
            <Button
              onClick={handleVerify}
              disabled={isSaving || !number.trim()}
              className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
            >
              {isSaving ? "Verificando…" : "Verificar"}
            </Button>
          </div>
          {verificationCode && (
            <p className="text-center text-2xl font-bold tracking-[0.3em]">
              {verificationCode}
              <span className="mt-2 block text-xs font-normal tracking-normal text-muted-foreground">
                Twilio llamará a ese número, en inglés, desde un número de
                Estados Unidos. Teclea este código.
              </span>
            </p>
          )}
          {pollExpired && (
            <p className="text-sm text-muted-foreground">
              La verificación ha caducado. Inténtalo de nuevo.
            </p>
          )}
        </div>
      )}
    </div>
  );
};
