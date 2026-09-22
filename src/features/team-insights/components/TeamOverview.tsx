import type { TeamMetrics, TeamRep } from "@/lib/team-insights";

export function TeamOverview({ metrics, reps }: { metrics: TeamMetrics; reps: TeamRep[] }) {
  return (
    <section aria-labelledby="team-activity">
      <h2 id="team-activity">Actividad</h2>
      <table>
        <tbody>
          <tr><th>Intentos</th><td>{metrics.attempts}</td></tr>
          <tr><th>Conversaciones</th><td>{metrics.connected}</td></tr>
          <tr><th>Reuniones acordadas</th><td>{metrics.meetings}</td></tr>
        </tbody>
      </table>
      <p>{reps.map((rep) => rep.name).join(", ")}</p>
    </section>
  );
}
