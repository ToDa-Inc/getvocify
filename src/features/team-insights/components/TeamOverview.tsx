import { activityLabel, type TeamMetrics, type TeamRep } from "@/lib/team-insights";

export function TeamOverview({ metrics, reps }: { metrics: TeamMetrics; reps: TeamRep[] }) {
  return (
    <section aria-labelledby="team-activity">
      <h2 id="team-activity">Actividad</h2>
      <table>
        <tbody>
          <tr><th>Intentos</th><td>{activityLabel(metrics.attempts)}</td></tr>
          <tr><th>Conversaciones</th><td>{activityLabel(metrics.connected)}</td></tr>
          <tr><th>Reuniones acordadas</th><td>{activityLabel(metrics.meetings)}</td></tr>
        </tbody>
      </table>
      <p>{reps.map((rep) => rep.name).join(", ")}</p>
    </section>
  );
}
