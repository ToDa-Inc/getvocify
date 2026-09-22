import type { TeamMetrics } from "@/lib/team-insights";

export function AdherenceBreakdown({ metrics }: { metrics: TeamMetrics }) {
  const label = metrics.adherence === null ? "Sin adherencia" : `${metrics.met} de ${metrics.applicable}`;
  return (
    <section aria-labelledby="team-adherence">
      <h2 id="team-adherence">Adherencia</h2>
      <p>{label}</p>
      <table>
        <tbody>
          <tr><th>Cumplidos</th><td>{metrics.met}</td></tr>
          <tr><th>Evaluables</th><td>{metrics.applicable}</td></tr>
        </tbody>
      </table>
    </section>
  );
}
