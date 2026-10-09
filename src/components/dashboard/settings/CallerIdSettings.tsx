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
import { callerIdOtpVisible, callerIdSetupPhase } from "@/lib/dial-target";

const POLL_MS = 3000;
const POLL_MAX_MS = 120_000;
// Server rejects these (Orden TDF/149/2025 art. 9, SETID 400); only hides the profile hint.
const ES_RESTRICTED_CLI = /^\+34(?:[67]|400)/;

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
  const [showAddForm, setShowAddForm] = useState(false);
  const [retrySend, setRetrySend] = useState(false);
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
    Boolean(whatsappPhone) &&
    !ES_RESTRICTED_CLI.test(whatsappPhone) &&
    !ids.some((c) => c.phoneNumber === whatsappPhone);
  const callableCount = ids.filter((c) => c.status === "verified" && !c.callBlocked).length;

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
        toast.success("This number is already verified");
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
      setRetrySend(false);
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
      toast.error(detail || "Could not start verification");
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
      toast.success("Number verified");
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
      toast.error(detail || "Could not confirm the code");
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
      toast.error("Could not set as default");
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
      toast.success("Number removed");
      await load();
    } catch {
      toast.error("Could not remove the number");
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

  const showOtp = callerIdOtpVisible({
    provider: config?.provider,
    enabled: config?.enabled,
    otpTarget,
  });
  const verifying = Boolean(hasPending || verificationCode || otpTarget);
  const phase = callerIdSetupPhase({
    numberCount: ids.length,
    verifying,
    showAddForm,
  });
  const showSendForm =
    Boolean(config?.enabled) && (phase === "add" || (phase === "verify" && retrySend));

  const sendForm = (
    <div className="space-y-3">
      {whatsappUnused && (
        <button
          type="button"
          className="text-xs text-beige hover:underline"
          onClick={() => setNumber(whatsappPhone)}
        >
          Use {whatsappPhone} from your profile
        </button>
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          placeholder="+34 910 111 222"
          className="rounded-full h-11"
        />
        <Button
          onClick={handleVerify}
          disabled={isSaving || !number.trim()}
          className="rounded-full bg-beige text-cream px-6"
        >
          {isSaving ? (
            <>
              <VocifySpinner size={12} />
              Sending…
            </>
          ) : (
            "Send code"
          )}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Caller ID</h3>
        <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
          The number people see when you call from Vocify. Verify it once, then dial from the
          extension.
        </p>
      </div>

      {!config?.enabled && (
        <p className="text-sm text-muted-foreground">
          Calling is not available in this environment.
        </p>
      )}

      {config?.enabled && config.hubspotLogging === false && (
        <p className="text-xs text-muted-foreground">
          Calls stay in Vocify until HubSpot call logging is configured.
        </p>
      )}

      {ids.length > 0 && (
        <ul className="space-y-3">
          {ids.map((row) => {
            const ready = row.status === "verified" && !row.callBlocked;
            const statusLabel = row.callBlocked
              ? null
              : ready
                ? row.isDefault
                  ? "Ready · default"
                  : "Ready"
                : "Waiting for the code";
            return (
              <li
                key={row.phoneNumber}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-border/40 px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{row.phoneNumber}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {[row.label, statusLabel, row.notice].filter(Boolean).join(" · ")}
                  </p>
                </div>
                {ready && !row.isDefault && callableCount > 1 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-8 rounded-full px-3 text-xs"
                    onClick={() => handleDefault(row.phoneNumber)}
                  >
                    Use as default
                  </Button>
                ) : null}
                {row.source !== "twilio" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-8 rounded-full px-3 text-xs"
                    onClick={() => setPendingDelete(row)}
                  >
                    Remove
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {phase === "ready" && (
        <button
          type="button"
          className="text-xs text-beige hover:underline"
          onClick={() => setShowAddForm(true)}
        >
          Add another number
        </button>
      )}

      {phase === "add" && config?.enabled && (
        <div className="space-y-4 rounded-2xl border border-border/40 bg-secondary/5 px-5 py-5">
          <div>
            <p className={THEME_TOKENS.typography.capsLabel}>Add a number</p>
            <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
              {isTelnyx
                ? "International format. We text a code to that phone — Vocify never invents or shows it."
                : "International format. You get a short call in English and type the code we show next."}
            </p>
          </div>
          {sendForm}
          {ids.length > 0 && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:underline"
              onClick={() => setShowAddForm(false)}
            >
              Cancel
            </button>
          )}
        </div>
      )}

      {phase === "verify" && (
        <div className="space-y-4 rounded-2xl border border-border/40 bg-secondary/5 px-5 py-5">
          <div>
            <p className={THEME_TOKENS.typography.capsLabel}>Finish verification</p>
            <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
              {isTelnyx
                ? `Enter the code sent to ${otpTarget}.`
                : verificationCode
                  ? "Answer the call and type this code on your keypad."
                  : "Answer the verification call, or send a new code if you missed it."}
            </p>
          </div>
          {verificationCode && !isTelnyx && (
            <p className="text-2xl font-semibold tracking-[0.25em] text-foreground">
              {verificationCode}
            </p>
          )}
          {showOtp && (
            <div className="flex flex-col sm:flex-row gap-2">
              <Input
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value)}
                placeholder="Code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={12}
                className="rounded-full h-11"
              />
              <Button
                type="button"
                onClick={handleConfirm}
                disabled={isConfirming || !otpCode.trim()}
                className="rounded-full bg-beige text-cream px-6"
              >
                {isConfirming ? (
                  <>
                    <VocifySpinner size={12} />
                    Confirming…
                  </>
                ) : (
                  "Confirm"
                )}
              </Button>
            </div>
          )}
          {pollExpired && !isTelnyx && (
            <p className="text-sm text-muted-foreground">The call expired. Send a new code.</p>
          )}
          {showSendForm ? (
            sendForm
          ) : (
            <button
              type="button"
              className="text-xs text-beige hover:underline"
              onClick={() => {
                if (otpTarget) setNumber(otpTarget);
                setRetrySend(true);
              }}
            >
              Send a new code
            </button>
          )}
        </div>
      )}

      <ConfirmAction
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this number?"
        description={
          pendingDelete
            ? `${pendingDelete.phoneNumber} will no longer be used as caller ID.`
            : ""
        }
        confirmLabel="Remove"
        pending={isDeleting}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
};
