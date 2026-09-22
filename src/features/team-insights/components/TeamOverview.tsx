import { useLanguage } from "@/lib/i18n";
import { activityLabel, type TeamMetrics, type TeamRep } from "@/lib/team-insights";

export function TeamOverview({ metrics, reps }: { metrics: TeamMetrics; reps: TeamRep[] }) {
  const { t } = useLanguage();
  return (
    <section aria-labelledby="team-activity">
      <h2 id="team-activity">Actividad</h2>
      <table>
        <tbody>
          <tr><th>Intentos</th><td>{activityLabel(metrics.attempts, t.product.unavailable)}</td></tr>
          <tr><th>Conversaciones</th><td>{activityLabel(metrics.connected, t.product.unavailable)}</td></tr>
          <tr><th>Reuniones acordadas</th><td>{activityLabel(metrics.meetings, t.product.unavailable)}</td></tr>
        </tbody>
      </table>
      {reps.length > 0 ? <p>{reps.map((rep) => rep.name).join(", ")}</p> : null}
    </section>
  );
}
