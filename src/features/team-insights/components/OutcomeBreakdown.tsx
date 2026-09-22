import { useLanguage } from "@/lib/i18n";
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
    <section aria-labelledby="team-outcomes">
      <h2 id="team-outcomes">{p.teamHeadingOutcomes}</h2>
      {partialWarning ? <p>{partialWarning}</p> : null}
      <table>
        <tbody>
          <tr><th>{p.teamOutcomesWon}</th><td>{metrics.won === null ? unavailable : metrics.won}</td></tr>
          <tr><th>{p.teamOutcomesLost}</th><td>{metrics.lost === null ? unavailable : metrics.lost}</td></tr>
          <tr><th>{unresolvedLabel}</th><td>{metrics.unresolvedWins}</td></tr>
          <tr><th>{p.teamOutcomesRate}</th><td>{winRate === null ? unavailable : winRate}</td></tr>
        </tbody>
      </table>
    </section>
  );
}
