import type { TeamMetrics } from "@/lib/team-insights";

export function OutcomeBreakdown({ metrics, winRate, unresolvedLabel, partialWarning }: {
  metrics: TeamMetrics;
  winRate: number | null;
  unresolvedLabel: string;
  partialWarning: string | null;
}) {
  return (
    <section aria-labelledby="team-outcomes">
      <h2 id="team-outcomes">Resultados</h2>
      {partialWarning ? <p>{partialWarning}</p> : null}
      <table>
        <tbody>
          <tr><th>Ganados</th><td>{metrics.won === null ? "No disponible" : metrics.won}</td></tr>
          <tr><th>Perdidos</th><td>{metrics.lost === null ? "No disponible" : metrics.lost}</td></tr>
          <tr><th>{unresolvedLabel}</th><td>{metrics.unresolvedWins}</td></tr>
          <tr><th>Tasa</th><td>{winRate === null ? "No disponible" : winRate}</td></tr>
        </tbody>
      </table>
    </section>
  );
}
