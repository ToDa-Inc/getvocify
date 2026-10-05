import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import { Switch } from "@/components/ui/switch";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { calendarApi, calendarKeys, type CalendarProvider, type CalendarState } from "@/lib/api/calendar";
import googleCalendarLogo from "@/assets/brands/google-calendar.svg";
import outlookLogo from "@/assets/brands/outlook.svg";

const PROVIDER: Record<CalendarProvider, { name: string; logo: string }> = {
  google: { name: "Google Calendar", logo: googleCalendarLogo },
  microsoft: { name: "Outlook", logo: outlookLogo },
};

/** The provider's own logo on the same tile the CRM list uses. */
function ProviderLogo({ provider }: { provider: CalendarProvider }) {
  return (
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border/50 bg-card p-2.5 shadow-xs">
      <img src={PROVIDER[provider].logo} alt="" className="h-full w-full object-contain" />
    </div>
  );
}

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

  const { data, isLoading } = useQuery({ queryKey: calendarKeys.state, queryFn: calendarApi.get, enabled });

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
  if (!enabled) return null;
  if (isLoading || !data) {
    return (
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.interaction.pageLoad}`}>
        <VocifyLoader size="md" />
      </div>
    );
  }

  const connectedProvider = connection ? PLATFORM_PROVIDER[connection.platform] : null;
  const lost = connection?.status === "disconnected";

  return (
    <div id="calendar" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-6 p-6 md:p-8`}>
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.calendarTitle}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t.product.calendarHint}</p>
      </div>

      {connection && connectedProvider ? (
        <div className="overflow-hidden rounded-xl border border-border/60">
          <div className="flex items-center gap-4 px-4 py-4">
            <ProviderLogo provider={connectedProvider} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm text-foreground">{PROVIDER[connectedProvider].name}</p>
                {connection.status === "connected" ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden />
                    {t.product.calendarStatusConnected}
                  </span>
                ) : lost ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
                    <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-hidden />
                    {t.product.calendarStatusDisconnected}
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 truncate text-[13px] text-muted-foreground">
                {connection.email ? (
                  connection.email
                ) : lost ? (
                  t.product.calendarDisconnected
                ) : (
                  <span className="inline-flex items-center gap-1.5">
                    <VocifySpinner />
                    {t.product.calendarConnecting}
                  </span>
                )}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {lost && providers.includes(connectedProvider) ? (
                <Button size="sm" disabled={redirecting !== null} onClick={() => connect(connectedProvider)}>
                  {t.product.calendarReconnect}
                </Button>
              ) : null}
              <IconAction label={t.product.calendarDisconnect} tone="danger" onClick={() => setConfirmOpen(true)}>
                <Unplug className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-4 border-t border-border/60 bg-secondary/[0.03] px-4 py-3.5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center" aria-hidden>
              <Bot className="h-5 w-5 text-beige" strokeWidth={1.5} />
            </span>
            <span className="min-w-0 flex-1 text-sm text-foreground">{t.product.calendarAutoJoin}</span>
            <Switch
              checked={connection.auto_join}
              disabled={lost}
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
              <ProviderLogo provider={provider} />
              <p className="min-w-0 flex-1 text-sm text-foreground">{PROVIDER[provider].name}</p>
              <Button size="sm" disabled={redirecting !== null} onClick={() => connect(provider)}>
                {redirecting === provider ? <VocifySpinner tone="onFill" /> : null}
                {t.product.calendarConnect}
              </Button>
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
