import { useLanguage } from "@/lib/i18n";
import { activityLabel, type TeamMetrics, type TeamRep } from "@/lib/team-insights";

export function TeamOverview({ metrics, reps }: { metrics: TeamMetrics; reps: TeamRep[] }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <section aria-labelledby="team-activity">
      <h2 id="team-activity">{p.teamHeadingActivity}</h2>
      <table>
        <tbody>
          <tr><th>{p.teamActivityAttempts}</th><td>{activityLabel(metrics.attempts, p.unavailable)}</td></tr>
          <tr><th>{p.teamActivityConnected}</th><td>{activityLabel(metrics.connected, p.unavailable)}</td></tr>
          <tr><th>{p.teamActivityMeetings}</th><td>{activityLabel(metrics.meetings, p.unavailable)}</td></tr>
        </tbody>
      </table>
      {reps.length > 0 ? <p>{reps.map((rep) => rep.name).join(", ")}</p> : null}
    </section>
  );
}
