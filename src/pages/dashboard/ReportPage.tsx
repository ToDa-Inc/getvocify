import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import { reportPagePresentation, type ReportSnapshot } from "@/lib/report-snapshot";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

function ActivityBar({ width, label }: { width: number | null; label: string }) {
  if (width == null) return null;
  return (
    <div className="space-y-1">
      <span className={THEME_TOKENS.typography.capsLabel}>{label}</span>
      <div className="h-2 w-full max-w-md rounded-full bg-secondary">
        <div className="h-2 rounded-full bg-beige" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export default function ReportPage() {
  const { t } = useLanguage();
  const { id } = useParams();
  const query = useQuery({
    queryKey: ["report", id],
    queryFn: () =>
      api.get<{ snapshot: ReportSnapshot; report_type: string }>(`/reports/${id}`),
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

  const weekly = query.data.report_type === "weekly";
  const view = reportPagePresentation(query.data.snapshot, {
    weekly,
    unavailable: t.product.unavailable,
  });
  const coachingText = view.coaching?.trim();
  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product.reportTitle}</h1>
      <dl className="grid gap-3 sm:grid-cols-2">
        {view.rows.map((row) => (
          <div key={row.cellKey} className="rounded-xl border border-border/70 bg-card px-4 py-3">
            <dt className="text-[13px] text-muted-foreground">{t.product[row.labelKey]}</dt>
            <dd className="mt-1 text-2xl tracking-tight">{row.value}</dd>
          </div>
        ))}
      </dl>
      {weekly && view.bars ? (
        <section className="space-y-4">
          <ActivityBar
            width={view.bars.conversationsOfAttempts}
            label={t.product.teamActivityConnected}
          />
          <ActivityBar
            width={view.bars.meetingsOfAttempts}
            label={t.product.teamActivityMeetings}
          />
          {view.activityTable ? (
            <dl className="grid gap-3 sm:grid-cols-3">
              {view.activityTable.map((row) => (
                <div key={row.cellKey} className="rounded-lg bg-secondary/40 px-3 py-3">
                  <dt className={THEME_TOKENS.typography.capsLabel}>{t.product[row.labelKey]}</dt>
                  <dd className="mt-1 text-2xl tracking-tight text-foreground">{row.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
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
    </main>
  );
}
