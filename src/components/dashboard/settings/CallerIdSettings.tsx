import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { Input } from "@/components/ui/input";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useAuth } from "@/features/auth";
import { callsApi } from "@/features/calls/api";
import { useCallingConfig } from "@/features/calls/useCallingConfig";
import type { CallerId } from "@/features/calls/types";
import { ApiError } from "@/shared/lib/api-client";
import { callerIdFormVisible, callerIdOtpVisible } from "@/lib/dial-target";

const POLL_MS = 3000;
const POLL_MAX_MS = 120_000;

export const CallerIdSettings = () => {
  const { user } = useAuth();
  const { config, isLoading, reload, setConfig } = useCallingConfig();
  const [number, setNumber] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [verificationCode, setVerificationCode] = useState<string | null>(null);
  const [otpPhone, setOtpPhone] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);
  const [pollExpired, setPollExpired] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CallerId | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const pollUntilRef = useRef<number | null>(null);
  const pollIdRef = useRef<number | null>(null);

  const load = useCallback(async () => reload(), [reload]);

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
  const isTelnyx = config?.provider === "telnyx";
  const pendingRow = ids.find((c) => c.status === "pending") ?? null;
  const hasPending = Boolean(pendingRow);
  const otpTarget = otpPhone || pendingRow?.phoneNumber || null;

  useEffect(() => {
    if (!hasPending || !config?.enabled || isTelnyx) {
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
  }, [hasPending, config?.enabled, isTelnyx, load]);

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
        setOtpPhone(null);
        setOtpCode("");
        toast.success("Este número ya está verificado");
      } else if (result.needsCodeSubmit) {
        setVerificationCode(null);
        setOtpPhone(result.phoneNumber);
        setOtpCode("");
      } else if (result.verificationCode) {
        setVerificationCode(result.verificationCode);
        setOtpPhone(null);
      } else {
        setVerificationCode(null);
        setOtpPhone(null);
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

  const handleConfirm = async () => {
    const phone = otpTarget;
    const code = otpCode.trim();
    if (!phone || !code) return;
    try {
      setIsConfirming(true);
      await callsApi.confirmCallerId(phone, code);
      setOtpPhone(null);
      setOtpCode("");
      toast.success("Número verificado");
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
      toast.error(detail || "No se pudo confirmar el código");
    } finally {
      setIsConfirming(false);
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

  const handleDelete = async () => {
    if (!pendingDelete) return;
    try {
      setIsDeleting(true);
      await callsApi.deleteCallerId(pendingDelete.phoneNumber);
      if (otpPhone === pendingDelete.phoneNumber) {
        setOtpPhone(null);
        setOtpCode("");
      }
      setPendingDelete(null);
      toast.success("Número eliminado");
      await load();
    } catch {
      toast.error("No se pudo eliminar el número");
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading caller ID..." />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Caller ID</h3>
        <p className="text-xs text-muted-foreground mt-1">
          {isTelnyx
            ? "El número que verán tus prospectos. Te enviaremos un código a ese número; introdúcelo aquí."
            : "El número que verán tus prospectos. Twilio te llamará, en inglés, y teclearás un código."}
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
          {isTelnyx
            ? "Verifica tu número una vez. Te enviaremos un código; introdúcelo aquí. Vocify nunca genera ni muestra ese código."
            : "Verifica tu número una vez. Twilio te llamará, en inglés, desde un número de Estados Unidos, y teclearás un código."}
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
                  onClick={() => setPendingDelete(row)}
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
              {isSaving ? (
                <>
                  <VocifySpinner size={12} />
                  Verificando…
                </>
              ) : (
                "Verificar"
              )}
            </Button>
          </div>
          {verificationCode && !isTelnyx && (
            <p className="text-center text-2xl font-bold tracking-[0.3em]">
              {verificationCode}
              <span className="mt-2 block text-xs font-normal tracking-normal text-muted-foreground">
                Twilio llamará a ese número, en inglés, desde un número de
                Estados Unidos. Teclea este código.
              </span>
            </p>
          )}
          {callerIdOtpVisible({
            provider: config?.provider,
            enabled: config?.enabled,
            otpTarget,
          }) && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Introduce el código enviado a {otpTarget}. Vocify nunca genera
                ni muestra ese código.
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="Código"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={12}
                  className="rounded-full h-11"
                />
                <Button
                  type="button"
                  onClick={handleConfirm}
                  disabled={isConfirming || !otpCode.trim()}
                  className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
                >
                  {isConfirming ? (
                    <>
                      <VocifySpinner size={12} />
                      Confirmando…
                    </>
                  ) : (
                    "Confirmar código"
                  )}
                </Button>
              </div>
            </div>
          )}
          {pollExpired && !isTelnyx && (
            <p className="text-sm text-muted-foreground">
              La verificación ha caducado. Inténtalo de nuevo.
            </p>
          )}
        </div>
      )}

      <ConfirmAction
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="¿Eliminar este número?"
        description={
          pendingDelete
            ? `${pendingDelete.phoneNumber} dejará de usarse como caller ID.`
            : ""
        }
        confirmLabel="Eliminar"
        pending={isDeleting}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
};
