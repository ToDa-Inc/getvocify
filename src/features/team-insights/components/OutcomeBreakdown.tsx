import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { TeamMetrics } from "@/lib/team-insights";

export function OutcomeBreakdown({ metrics, winRate, unresolvedLabel, partialWarning }: {
  metrics: TeamMetrics;
  winRate: number | null;
  unresolvedLabel: string;
  partialWarning: string | null;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const unavailable = p.unavailable;
  return (
    <section aria-labelledby="team-outcomes" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`}>
      <h2 id="team-outcomes" className={THEME_TOKENS.typography.sectionTitle}>{p.teamHeadingOutcomes}</h2>
      {partialWarning ? <p className={THEME_TOKENS.typography.body}>{partialWarning}</p> : null}
      <dl className="grid gap-3 sm:grid-cols-2">
        {[
          [p.teamOutcomesWon, metrics.won === null ? unavailable : metrics.won],
          [p.teamOutcomesLost, metrics.lost === null ? unavailable : metrics.lost],
          [unresolvedLabel, metrics.unresolvedWins],
          [p.teamOutcomesRate, winRate === null ? unavailable : winRate],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <dt className={THEME_TOKENS.typography.capsLabel}>{label}</dt>
            <dd className="text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
