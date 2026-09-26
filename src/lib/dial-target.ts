export const CALL_STATES = {
  IDLE: "idle",
  CONNECTING: "connecting",
  RINGING: "ringing",
  ACTIVE: "active",
  ENDING: "ending",
} as const;

export type CallState = (typeof CALL_STATES)[keyof typeof CALL_STATES];

const SEPARATORS = /[\s().\-/]/g;
const DIGITS_ONLY = /^\d+$/;
const E164 = /^\+[1-9]\d{7,14}$/;

export function normalizeDialTarget(
  raw: unknown,
  defaultCountryCode = "34",
): string | null {
  if (typeof raw !== "string") return null;
  let value = raw.replace(SEPARATORS, "").trim();
  if (!value) return null;

  if (value.startsWith("00")) {
    value = `+${value.slice(2)}`;
  } else if (!value.startsWith("+")) {
    if (!DIGITS_ONLY.test(value)) return null;

    if (value.startsWith(defaultCountryCode)) {
      const remaining = value.slice(defaultCountryCode.length);
      if (remaining.length >= 8) {
        return null;
      }
    }

    value = `+${defaultCountryCode}${value.replace(/^0+/, "")}`;
  }

  return E164.test(value) ? value : null;
}

export function canSendDigits(callState: string | undefined): boolean {
  return callState === CALL_STATES.ACTIVE;
}

export function canMute(callState: string | undefined): boolean {
  return callState === CALL_STATES.ACTIVE;
}

export function callButtonLabel(callState: string | undefined): string {
  switch (callState) {
    case CALL_STATES.CONNECTING:
      return "Conectando…";
    case CALL_STATES.RINGING:
      return "Llamando…";
    case CALL_STATES.ACTIVE:
      return "Colgar";
    case CALL_STATES.ENDING:
      return "Colgando…";
    default:
      return "Llamar";
  }
}

export function formatLiveDuration(elapsedMs: number): string {
  const total = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function isInCall(callState: string | undefined): boolean {
  return Boolean(callState && callState !== CALL_STATES.IDLE);
}

export function floatingDialerChrome(
  open: boolean,
  callState: CallState | undefined,
): { sheet: boolean; fab: boolean } {
  return {
    sheet: open,
    fab: !open && isInCall(callState),
  };
}

/** Panel placement shows the in-call bar at the column foot; floating keeps the FAB. */
export function dialerChrome(
  placement: "floating" | "panel",
  open: boolean,
  callState: CallState | undefined,
): { sheet: boolean; fab: boolean; panelBar: boolean } {
  const inFlight = isInCall(callState);
  if (placement === "panel") {
    return { sheet: open && !inFlight, fab: false, panelBar: inFlight || open };
  }
  const floating = floatingDialerChrome(open, callState);
  return { ...floating, panelBar: false };
}

export function formatCallerIdDisplay(e164: string): string {
  const digits = (e164 || "").replace(/\D/g, "");
  if (e164.startsWith("+34") && digits.length === 11) {
    const national = digits.slice(2);
    return `+34 ${national.slice(0, 3)} ${national.slice(3, 5)} ${national.slice(5, 7)} ${national.slice(7)}`;
  }
  return e164;
}

export function dialTargetFromContact(
  contact: { phone?: string | null } | null | undefined,
  defaultCountryCode = "34",
): string | null {
  return normalizeDialTarget(contact?.phone, defaultCountryCode);
}

export function contactInitials(name: string | null | undefined): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function callerIdFormVisible(args: {
  isLoading: boolean;
  enabled?: boolean;
}): boolean {
  return !args.isLoading;
}

/** Which caller-ID panel to show: add a number, finish verification, or the ready list. */
export function callerIdSetupPhase(args: {
  numberCount: number;
  verifying: boolean;
  showAddForm: boolean;
}): "add" | "verify" | "ready" {
  if (args.verifying) return "verify";
  if (args.numberCount === 0 || args.showAddForm) return "add";
  return "ready";
}

/** Telnyx OTP field: pending number exists, calling is on, provider is Telnyx. */
export function callerIdOtpVisible(args: {
  provider?: string;
  enabled?: boolean;
  otpTarget: string | null;
}): boolean {
  return args.provider === "telnyx" && Boolean(args.enabled) && Boolean(args.otpTarget);
}
