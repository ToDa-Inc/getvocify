import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Settings } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { ROUTES } from "@/shared/lib/constants";
import { useCallingConfig } from "@/features/calls/useCallingConfig";
import { useLanguage } from "@/lib/i18n";
import { CALL_STATES, callButtonLabel, dialerDock, type CallState } from "@/lib/dial-target";
import type { CallEndedPayload, DialerFocus } from "@/features/calling/DialerFocusProvider";
import { TodayDialerCards } from "@/features/today/components/TodayDialerCards";
import { DockHeader, DockPanel } from "@/components/dashboard/RightDock";
import { DashboardDialer } from "./DashboardDialer";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCallStateChange?: (state: CallState) => void;
  focusContact?: DialerFocus | null;
  onFocusHandled?: () => void;
  onCallEnded?: (payload: CallEndedPayload) => void;
  onLiveReport?: (live: {
    state: CallState;
    elapsed: string;
    contact?: DialerFocus | null;
    callSid?: string | null;
  }) => void;
};

/**
 * The call panel, docked on the right. It stays mounted while a call is in progress even if the
 * panel is closed: the dialer holds the phone connection, and the edge tab shows the call is live.
 */
export const DialerDock = ({
  open,
  onOpenChange,
  onCallStateChange,
  focusContact = null,
  onFocusHandled,
  onCallEnded,
  onLiveReport,
}: Props) => {
  const { t } = useLanguage();
  const p = t.product;
  const navigate = useNavigate();
  const { config, isLoading } = useCallingConfig();
  const [live, setLive] = useState<{ state: CallState; elapsed: string }>({
    state: CALL_STATES.IDLE,
    elapsed: "0:00",
  });

  const dock = dialerDock(open, live.state);
  const mounted = open || dock.liveTab;
  const enabled = Boolean(config?.enabled);
  const statusLabel =
    live.state === CALL_STATES.ACTIVE
      ? live.elapsed
      : live.state === CALL_STATES.IDLE
        ? p.dialReadyToCall
        : callButtonLabel(live.state);

  const dialerBody = (
    <DashboardDialer
      callerIds={config?.callerIds || []}
      focusContact={focusContact}
      onFocusHandled={onFocusHandled}
      onRequestClose={() => onOpenChange(false)}
      compact={false}
      showBrief
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
    <DockPanel open={open} label={p.navCall}>
      <DockHeader
        title={p.navCall}
        status={isLoading ? undefined : statusLabel}
        closeLabel={p.askClose}
        onClose={() => onOpenChange(false)}
        actions={
          <IconAction
            label="Caller ID"
            onClick={() => {
              onOpenChange(false);
              navigate(ROUTES.CALLING);
            }}
          >
            <Settings aria-hidden className="h-4 w-4" strokeWidth={1.5} />
          </IconAction>
        }
      />
      <div className="app-scroll flex-1 overflow-y-auto px-4 pb-4 pt-3">
        {isLoading ? (
          <p className="py-10 text-center text-sm text-muted-foreground">Cargando…</p>
        ) : enabled ? (
          <>
            {dialerBody}
            {live.state === CALL_STATES.IDLE ? <TodayDialerCards /> : null}
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
    </DockPanel>
  );
};
