import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import { reportKeys, reportsApi } from "@/lib/api/reports";
import { reportAdherenceTrend, reportPagePresentation, reportTitleKey, type ReportPageDay } from "@/lib/report-snapshot";
import { THEME_TOKENS } from "@/lib/theme/tokens";

function formatDate(iso: string | undefined, locale: string, timeZone: string | undefined, withTime = false): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const options: Intl.DateTimeFormatOptions = withTime
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { weekday: "short", day: "numeric", month: "short" };
  try {
    return date.toLocaleString(locale, { ...options, timeZone });
  } catch {
    return date.toLocaleString(locale, options);
  }
}

function DayTable({ days, locale }: { days: ReportPageDay[]; locale: string }) {
  const { t } = useLanguage();
  const peak = Math.max(1, ...days.map((day) => day.connected ?? 0));
  return (
    <section className="space-y-2">
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportByDay}</h2>
      <table className="w-full max-w-xl text-sm">
        <thead>
          <tr className="text-left text-[13px] text-muted-foreground">
            <th className="py-1 font-normal">{t.product.reportDay}</th>
            <th className="py-1 font-normal">{t.product.teamActivityConnected}</th>
            <th className="py-1 font-normal">{t.product.teamActivityMeetings}</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date} className="border-t border-border/60">
              <td className="py-2 pr-4">{formatDate(`${day.date}T12:00:00Z`, locale, "UTC")}</td>
              {day.covered ? (
                <>
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      <span className="w-6 tabular-nums">{day.connected}</span>
                      <span
                        aria-hidden
                        className="h-1.5 rounded-full bg-beige"
                        style={{ width: `${((day.connected ?? 0) / peak) * 8}rem` }}
                      />
                    </div>
                  </td>
                  <td className="py-2 tabular-nums">{day.meetings}</td>
                </>
              ) : (
                <td colSpan={2} className="py-2 text-muted-foreground">{t.product.reportDayNotIncluded}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function ReportPage() {
  const { t } = useLanguage();
  const { id } = useParams();
  const query = useQuery({
    queryKey: reportKeys.report(id),
    queryFn: () => reportsApi.get(id as string),
    enabled: Boolean(id),
    retry: false,
  });

  if (query.isPending) {
    return (
      <main className={`max-w-5xl mx-auto space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product.reportTitle}</h1>
        <p className={THEME_TOKENS.typography.body}>{t.product.reportLoading}</p>
      </main>
    );
  }

  if (query.isError) {
    return (
      <main className={`max-w-5xl mx-auto space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product.reportTitle}</h1>
        <p className={THEME_TOKENS.typography.body}>{t.product.reportFailed}</p>
      </main>
    );
  }

  const report = query.data;
  const snapshot = report.snapshot;
  const locale = t.product.hourLocale;
  const view = reportPagePresentation(snapshot, {
    unavailable: t.product.unavailable,
    stepsTemplate: t.product.reportAdherenceSteps,
    channelCopy: {
      call: { one: t.product.reportChannelCallOne, other: t.product.reportChannelCallOther },
      meeting: { one: t.product.reportChannelMeetingOne, other: t.product.reportChannelMeetingOther },
      visit: { one: t.product.reportChannelVisitOne, other: t.product.reportChannelVisitOther },
    },
  });
  const trend = reportAdherenceTrend(snapshot, {
    team: t.product.teamTitle,
    unscored: t.product.reportTrendUnscored,
    stepsTemplate: t.product.teamAdherenceOf,
  });
  const coachingText = view.coaching?.trim();
  const objectionLabels = t.product.objections as Record<string, string>;
  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <header className="space-y-1">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product[reportTitleKey(report)]}</h1>
        {snapshot.generated_at ? (
          <p className="text-[13px] text-muted-foreground">
            {t.product.reportGeneratedAt.replace(
              "{date}",
              formatDate(snapshot.generated_at, locale, snapshot.timezone, true),
            )}
          </p>
        ) : null}
      </header>
      <dl className="grid gap-3 sm:grid-cols-2">
        {view.rows.map((row) => (
          <div key={row.cellKey} className="rounded-xl border border-border/70 bg-card px-4 py-3">
            <dt className="text-[13px] text-muted-foreground">{t.product[row.labelKey]}</dt>
            <dd className="mt-1 text-2xl tracking-tight">{row.value}</dd>
          </div>
        ))}
      </dl>
      {view.channelsLine ? <p className="text-[13px] text-muted-foreground">{view.channelsLine}</p> : null}
      {snapshot.sample_limited ? <p className="text-[13px] text-muted-foreground">{t.product.sampleLimited}</p> : null}
      {view.days.length ? <DayTable days={view.days} locale={locale} /> : null}
      {trend ? (
        <section className="space-y-2">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportAdherenceByWeek}</h2>
          <table className="w-full max-w-2xl text-sm">
            <thead>
              <tr className="text-left text-[13px] text-muted-foreground">
                <th className="py-1 font-normal" />
                {trend.weeks.map((week) => (
                  <th key={week} className="py-1 font-normal">
                    {new Date(`${week}T12:00:00Z`).toLocaleDateString(locale, { day: "numeric", month: "short", timeZone: "UTC" })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trend.rows.map((row) => (
                <tr key={row.name} className="border-t border-border/60">
                  <th scope="row" className="py-2 pr-4 text-left font-normal">{row.name}</th>
                  {row.cells.map((cell, index) => (
                    <td key={trend.weeks[index]} className="py-2 pr-4 tabular-nums">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {trend.sampleLimited ? <p className="text-[13px] text-muted-foreground">{t.product.reportTrendSampleNote}</p> : null}
        </section>
      ) : null}
      {view.objections ? (
        <section className="space-y-2">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportTopObjections}</h2>
          <table className="w-full max-w-xs text-sm">
            <tbody>
              {view.objections.map((item) => (
                <tr key={item.name} className="border-t border-border/60">
                  <td className="py-2">{objectionLabels[item.name] ?? item.name}</td>
                  <td className="py-2 text-right tabular-nums">{item.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      {coachingText ? <p className={THEME_TOKENS.typography.body}>{coachingText}</p> : null}
      {view.exampleLinks.length ? (
        <ul className="space-y-2">
          {view.exampleLinks.map((href) => (
            <li key={href}>
              <Link className="text-sm text-beige" to={href}>{href}</Link>
            </li>
          ))}
        </ul>
      ) : null}
      <Link to="/dashboard/settings/brief#report-preferences" className="inline-block text-[13px] text-muted-foreground hover:text-foreground">
        {t.product.reportConfigure}
      </Link>
    </main>
  );
}
