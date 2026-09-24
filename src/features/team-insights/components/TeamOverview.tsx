import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { activityLabel, type TeamMetrics, type TeamRep } from "@/lib/team-insights";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`;

export function TeamOverview({ metrics, reps }: { metrics: TeamMetrics; reps: TeamRep[] }) {
  const { t } = useLanguage();
  const p = t.product;
  const rows = [
    [p.teamActivityAttempts, activityLabel(metrics.attempts, p.unavailable)],
    [p.teamActivityConnected, activityLabel(metrics.connected, p.unavailable)],
    [p.teamActivityMeetings, activityLabel(metrics.meetings, p.unavailable)],
  ] as const;
  return (
    <section aria-labelledby="team-activity" className={card}>
      <h2 id="team-activity" className={THEME_TOKENS.typography.sectionTitle}>{p.teamHeadingActivity}</h2>
      <dl className="grid gap-3 sm:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-secondary/40 px-3 py-3">
            <dt className={THEME_TOKENS.typography.capsLabel}>{label}</dt>
            <dd className="mt-1 text-2xl tracking-tight text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {reps.length > 0 ? <p className={THEME_TOKENS.typography.body}>{reps.map((rep) => rep.name).join(", ")}</p> : null}
    </section>
  );
}
