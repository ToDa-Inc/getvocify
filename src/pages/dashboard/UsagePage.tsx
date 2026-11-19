import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { es as esLocale } from "date-fns/locale";
import { Clock, PhoneOutgoing, Phone, RefreshCw, Video } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { memosApi, memoKeys } from "@/features/memos/api";
import type { UsageDay } from "@/features/memos/types";
import { useLanguage } from "@/lib/i18n";

const COPY = {
  EN: {
    loading: "Loading usage…",
    failed: "Couldn't load your usage",
    retry: "Try again",
    retrying: "Retrying…",
    month: (label: string) => `${label} so far`,
    calls: "Calls",
    meetings: "Meetings",
    recorded: "Recorded",
    crm: "CRM updates",
    dialer: "Dialer",
    daily: "Last 30 days",
    dailyHint: (total: number) => `${total} interactions recorded since you started`,
    recent: "Latest activity",
    none: "Nothing yet.",
    synced: "Synced to CRM",
    created: "Recorded",
    untitled: "No name yet",
  },
  ES: {
    loading: "Cargando el uso…",
    failed: "No se pudo cargar tu uso",
    retry: "Reintentar",
    retrying: "Reintentando…",
    month: (label: string) => `${label} hasta hoy`,
    calls: "Llamadas",
    meetings: "Reuniones",
    recorded: "Grabado",
    crm: "Actualizaciones de CRM",
    dialer: "Marcador",
    daily: "Últimos 30 días",
    dailyHint: (total: number) => `${total} interacciones grabadas desde que empezaste`,
    recent: "Actividad reciente",
    none: "Aún nada.",
    synced: "Guardada en el CRM",
    created: "Grabada",
    untitled: "Sin nombre aún",
  },
} as const;

/** Minutes as "45 min" or "3h 20m": short enough to stay on one line in a tile. */
function duration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const rest = minutes % 60;
  return rest ? `${Math.floor(minutes / 60)}h ${rest}m` : `${minutes / 60}h`;
}

function DailyBars({ days, locale }: { days: UsageDay[]; locale: string }) {
  const max = Math.max(1, ...days.map((d) => d.interactions));
  return (
    <div className="flex h-32 items-end gap-[3px]" role="img" aria-label={days.map((d) => `${d.date}: ${d.interactions}`).join(", ")}>
      {days.map((day) => {
        const label = new Date(`${day.date}T12:00:00Z`).toLocaleDateString(locale, { day: "numeric", month: "short" });
        return (
          <div key={day.date} className="group relative flex h-full flex-1 items-end">
            <div
              className={`w-full rounded-t-[3px] transition-colors duration-150 ${day.interactions ? "bg-beige/70 group-hover:bg-beige" : "bg-foreground/5"}`}
              style={{ height: day.interactions ? `${Math.max(6, (day.interactions / max) * 100)}%` : "3px" }}
            />
            <span className="pointer-events-none absolute -top-7 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-card px-1.5 py-0.5 text-[11px] text-foreground opacity-0 shadow-soft transition-opacity group-hover:opacity-100">
              {label} · {day.interactions}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const UsagePage = () => {
  const { language } = useLanguage();
  const copy = COPY[language === "ES" ? "ES" : "EN"];
  const locale = language === "ES" ? "es-ES" : "en-GB";
  const { data: usage, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: memoKeys.usage(),
    queryFn: () => memosApi.getUsage(),
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label={copy.loading} />
      </div>
    );
  }

  if (isError || !usage) {
    return (
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-4 p-12 text-center`}>
        <p className="font-medium text-foreground">{copy.failed}</p>
        <p className="text-sm text-muted-foreground">{(error as Error)?.message}</p>
        <Button size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? (
            <>
              <VocifySpinner size={12} />
              {copy.retrying}
            </>
          ) : (
            copy.retry
          )}
        </Button>
      </div>
    );
  }

  const monthLabel = new Date(`${usage.period_start}T12:00:00Z`).toLocaleDateString(locale, { month: "long" });
  const tiles = [
    { icon: Phone, label: copy.calls, value: String(usage.calls) },
    { icon: Video, label: copy.meetings, value: String(usage.meetings) },
    { icon: Clock, label: copy.recorded, value: duration(usage.recorded_minutes) },
    { icon: RefreshCw, label: copy.crm, value: String(usage.crm_updates) },
    ...(usage.dialer_minutes ? [{ icon: PhoneOutgoing, label: copy.dialer, value: duration(usage.dialer_minutes) }] : []),
  ];

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <section className="space-y-3">
        <p className={`${THEME_TOKENS.typography.capsLabel} first-letter:uppercase`}>{copy.month(monthLabel)}</p>
        {/* One row on a wide screen, the dialer's tile included when there is one. */}
        <div className={`grid grid-cols-2 gap-3 ${tiles.length > 4 ? "sm:grid-cols-5" : "sm:grid-cols-4"}`}>
          {tiles.map((tile) => (
            <div key={tile.label} className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-4`}>
              <tile.icon className="h-4 w-4 text-beige" strokeWidth={1.75} aria-hidden />
              <p className="mt-3 whitespace-nowrap text-2xl font-semibold tabular-nums tracking-tight text-foreground">{tile.value}</p>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">{tile.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-5 p-5`}>
        <div className="flex items-baseline justify-between gap-3">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{copy.daily}</h2>
          <p className="text-[12.5px] text-muted-foreground">{copy.dailyHint(usage.total_interactions)}</p>
        </div>
        <DailyBars days={usage.daily} locale={locale} />
      </section>

      <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-3`}>{copy.recent}</h2>
        {usage.recent_activity.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{copy.none}</p>
        ) : (
          <ul className="divide-y divide-border/50">
            {usage.recent_activity.map((activity) => (
              <li key={`${activity.time}-${activity.company}`} className="flex items-center justify-between gap-4 py-2.5">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${activity.type === "sync" ? "bg-success" : "bg-beige"}`} aria-hidden />
                  <p className="truncate text-[13.5px] text-foreground">{activity.company || copy.untitled}</p>
                  <span className="shrink-0 text-[12.5px] text-muted-foreground">{activity.type === "sync" ? copy.synced : copy.created}</span>
                </div>
                <span className="shrink-0 text-[12.5px] text-muted-foreground">
                  {formatDistanceToNow(new Date(activity.time), { addSuffix: true, locale: language === "ES" ? esLocale : undefined })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};

export default UsagePage;
