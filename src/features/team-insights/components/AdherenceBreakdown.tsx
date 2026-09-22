import { adherenceBarRatio, type TeamMetrics } from "@/lib/team-insights";

export function AdherenceBreakdown({ metrics }: { metrics: TeamMetrics }) {
  const label = metrics.adherence === null ? "Sin adherencia" : `${metrics.met} de ${metrics.applicable}`;
  const barRatio = adherenceBarRatio(metrics);
  return (
    <section aria-labelledby="team-adherence">
      <h2 id="team-adherence">Adherencia</h2>
      <p>{label}</p>
      {barRatio !== null ? (
        <div className="relative h-4 w-full max-w-md overflow-hidden rounded-full bg-secondary">
          <div className="h-full bg-primary" style={{ width: `${barRatio * 100}%` }} />
        </div>
      ) : null}
      <table>
        <tbody>
          <tr><th>Cumplidos</th><td>{metrics.met}</td></tr>
          <tr><th>Evaluables</th><td>{metrics.applicable}</td></tr>
        </tbody>
      </table>
      {metrics.sampleLimited ? (
        <p>Con menos de cinco conversaciones no hay conclusión.</p>
      ) : null}
    </section>
  );
}
