import { useState } from "react";
import { Link } from "react-router-dom";
import { Gear, Minus, Phone } from "@phosphor-icons/react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { ROUTES } from "@/shared/lib/constants";
import { useCallingConfig } from "@/features/calls/useCallingConfig";
import {
  CALL_STATES,
  callButtonLabel,
  dialerChrome,
  isInCall,
  type CallState,
} from "@/lib/dial-target";
import type { CallEndedPayload, DialerFocus } from "@/features/calling/DialerFocusProvider";
import { TodayDialerCards } from "@/features/today/components/TodayDialerCards";
import { DashboardDialer } from "./DashboardDialer";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCallStateChange?: (state: CallState) => void;
  focusContact?: DialerFocus | null;
  onFocusHandled?: () => void;
  placement?: "floating" | "panel";
  onCallEnded?: (payload: CallEndedPayload) => void;
  onLiveReport?: (live: {
    state: CallState;
    elapsed: string;
    contact?: DialerFocus | null;
    callSid?: string | null;
  }) => void;
};

export const FloatingDialer = ({
  open,
  onOpenChange,
  onCallStateChange,
  focusContact = null,
  onFocusHandled,
  placement = "floating",
  onCallEnded,
  onLiveReport,
}: Props) => {
  const { config, isLoading } = useCallingConfig();
  const [live, setLive] = useState<{ state: CallState; elapsed: string }>({
    state: CALL_STATES.IDLE,
    elapsed: "0:00",
  });

  const chrome = dialerChrome(placement, open, live.state);
  const mounted = open || chrome.fab || chrome.panelBar;
  const enabled = Boolean(config?.enabled);
  const statusLabel =
    live.state === CALL_STATES.ACTIVE
      ? live.elapsed
      : live.state === CALL_STATES.IDLE
        ? "Listo"
        : callButtonLabel(live.state);
  const fabLabel =
    live.state === CALL_STATES.ACTIVE ? live.elapsed : callButtonLabel(live.state);
  const visible = chrome.sheet || chrome.panelBar;

  const positionClass =
    placement === "panel"
      ? "fixed bottom-0 right-0 z-50 w-[400px] border-t border-border/40 bg-card/95 backdrop-blur-sm"
      : `fixed bottom-5 right-5 z-50 w-[340px] ${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container}`;

  const header =
    placement === "floating" || chrome.sheet ? (
      <div className="flex items-center gap-3 border-b border-border/40 px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium leading-none text-foreground">Call</p>
          <p className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">
            {isLoading ? "Cargando…" : statusLabel}
          </p>
        </div>
        <Link
          to={ROUTES.CALLING}
          aria-label="Caller ID"
          onClick={() => onOpenChange(false)}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <Gear size={16} weight="light" />
        </Link>
        <button
          type="button"
          aria-label="Cerrar dialer"
          onClick={() => onOpenChange(false)}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <Minus size={16} weight="light" />
        </button>
      </div>
    ) : null;

  const dialerBody = (
    <DashboardDialer
      callerIds={config?.callerIds || []}
      focusContact={focusContact}
      onFocusHandled={onFocusHandled}
      onRequestClose={() => onOpenChange(false)}
      compact={placement === "panel" && isInCall(live.state)}
      onCallEnded={onCallEnded}
      onLiveChange={(next) => {
        setLive(next);
        onCallStateChange?.(next.state);
        onLiveReport?.(next);
      }}
    />
  );

  if (!mounted) return null;

  return (
    <>
      <div
        className={`${positionClass} ${visible ? "" : "invisible pointer-events-none"}`}
        role={chrome.sheet ? "dialog" : undefined}
        aria-hidden={!visible}
        aria-label="Dialer"
      >
        {header}
        <div className={placement === "panel" && !chrome.sheet ? "px-4 py-3" : "px-4 pb-4 pt-3"}>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : enabled ? (
            <>
              {dialerBody}
              {placement === "floating" && live.state === CALL_STATES.IDLE ? <TodayDialerCards /> : null}
            </>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Las llamadas no están configuradas.{" "}
              <Link to={ROUTES.CALLING} className="text-beige hover:underline">
                Revisa Caller ID
              </Link>
            </p>
          )}
        </div>
      </div>

      {chrome.fab ? (
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          aria-label={`Llamada en curso, ${fabLabel}`}
          className={`fixed bottom-5 right-5 z-50 flex items-center gap-2 pl-3 pr-3.5 py-2 ${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.pill}`}
        >
          <Phone size={14} weight="light" className="text-beige" />
          <span className="text-[13px] font-medium tabular-nums text-foreground">{fabLabel}</span>
        </button>
      ) : null}
    </>
  );
};
