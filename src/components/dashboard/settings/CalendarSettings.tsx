import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { calendarApi, calendarKeys, type CalendarProvider, type CalendarState } from "@/lib/api/calendar";

const PROVIDER_NAME: Record<CalendarProvider, string> = {
  google: "Google Calendar",
  microsoft: "Outlook",
};

const PLATFORM_PROVIDER: Record<string, CalendarProvider> = {
  google_calendar: "google",
  microsoft_outlook: "microsoft",
};

/**
 * The rep's calendar for the Recall.ai meeting bot: connect Google Calendar or Outlook, then
 * one switch for whether the bot joins their meetings with people outside the company.
 * Its own settings tab (every role), behind RECALL_BOT_ENABLED.
 */
export const CalendarSettings = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [redirecting, setRedirecting] = useState<CalendarProvider | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const enabled = Boolean(user?.company?.features?.includes("RECALL_BOT_ENABLED"));

  const { data } = useQuery({ queryKey: calendarKeys.state, queryFn: calendarApi.get, enabled });

  useEffect(() => {
    const result = searchParams.get("calendar");
    if (!result) return;
    if (result === "connected") {
      toast.success(t.product.calendarConnected);
      queryClient.invalidateQueries({ queryKey: calendarKeys.state });
    } else {
      toast.error(
        searchParams.get("error") === "access_denied" ? t.product.calendarAccessDenied : t.product.calendarConnectFailed,
      );
    }
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the OAuth return query
  }, [searchParams]);

  const connect = async (provider: CalendarProvider) => {
    setRedirecting(provider);
    try {
      const { redirect_url } = await calendarApi.authorizeUrl(provider);
      window.location.href = redirect_url;
    } catch {
      setRedirecting(null);
      toast.error(t.product.calendarConnectFailed);
    }
  };

  const autoJoin = useMutation({
    mutationFn: calendarApi.setAutoJoin,
    onMutate: async (value: boolean) => {
      await queryClient.cancelQueries({ queryKey: calendarKeys.state });
      const previous = queryClient.getQueryData<CalendarState>(calendarKeys.state);
      if (previous?.connection) {
        queryClient.setQueryData<CalendarState>(calendarKeys.state, {
          ...previous,
          connection: { ...previous.connection, auto_join: value },
        });
      }
      return { previous };
    },
    onSuccess: (updated) => queryClient.setQueryData(calendarKeys.state, updated),
    onError: (_error, _value, context) => {
      if (context?.previous) queryClient.setQueryData(calendarKeys.state, context.previous);
      toast.error(t.product.calendarSaveFailed);
    },
  });

  const disconnect = useMutation({
    mutationFn: calendarApi.disconnect,
    onSuccess: () => {
      setConfirmOpen(false);
      queryClient.setQueryData<CalendarState>(calendarKeys.state, (prev) =>
        prev ? { ...prev, connection: null } : prev,
      );
    },
    onError: () => toast.error(t.product.calendarDisconnectFailed),
  });

  const connection = data?.connection ?? null;
  const providers = data?.providers ?? [];
  if (!enabled || !data) return null;

  const connectedProvider = connection ? PLATFORM_PROVIDER[connection.platform] : null;

  const connectButton = (provider: CalendarProvider, label: string) => (
    <Button
      size="sm"
      className="rounded-full bg-beige text-cream h-9 px-4"
      disabled={redirecting !== null}
      onClick={() => connect(provider)}
    >
      {label}
    </Button>
  );

  return (
    <div id="calendar" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-5 p-6 md:p-8`}>
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.calendarTitle}</h3>
        <p className="text-xs text-muted-foreground mt-1">{t.product.calendarHint}</p>
      </div>

      {connection && connectedProvider ? (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-secondary/5">
              <CalendarDays className="h-5 w-5 text-muted-foreground" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-foreground">{PROVIDER_NAME[connectedProvider]}</p>
              <p className="text-xs mt-0.5 truncate">
                {connection.status === "disconnected" ? (
                  <span className="text-warning">{t.product.calendarDisconnected}</span>
                ) : connection.email ? (
                  <span className="text-muted-foreground">{connection.email}</span>
                ) : (
                  <span className="text-muted-foreground">{t.product.calendarConnecting}</span>
                )}
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {connection.status === "disconnected" &&
                providers.includes(connectedProvider) &&
                connectButton(connectedProvider, t.product.calendarReconnect)}
              <IconAction label={t.product.calendarDisconnect} tone="danger" onClick={() => setConfirmOpen(true)}>
                <Unplug className="h-4 w-4" />
              </IconAction>
            </div>
          </div>

          <label className="flex items-center justify-between gap-4 border-t border-border/60 pt-4 text-sm">
            <span>{t.product.calendarAutoJoin}</span>
            <Switch
              checked={connection.auto_join}
              disabled={connection.status === "disconnected"}
              onCheckedChange={(checked) => autoJoin.mutate(checked)}
            />
          </label>
        </div>
      ) : providers.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t.product.calendarUnavailable}</p>
      ) : (
        <div className="divide-y divide-border/40">
          {providers.map((provider) => (
            <div key={provider} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-secondary/5">
                <CalendarDays className="h-5 w-5 text-muted-foreground" aria-hidden />
              </div>
              <p className="min-w-0 flex-1 text-sm text-foreground">{PROVIDER_NAME[provider]}</p>
              {connectButton(provider, t.product.calendarConnect)}
            </div>
          ))}
        </div>
      )}

      <ConfirmAction
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t.product.calendarDisconnectTitle}
        description={t.product.calendarDisconnectBody}
        confirmLabel={t.product.calendarDisconnectConfirm}
        tone="danger"
        pending={disconnect.isPending}
        onConfirm={() => disconnect.mutate()}
      />
    </div>
  );
};
