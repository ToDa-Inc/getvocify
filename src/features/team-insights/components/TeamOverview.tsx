import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { activityLabel, repFlowAdherenceText, type TeamMetrics, type TeamRep } from "@/lib/team-insights";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`;

export function TeamOverview({
  metrics,
  reps,
  showRepDetail = false,
}: {
  metrics: TeamMetrics;
  reps: TeamRep[];
  /** T13: MANAGER_HOME_ENABLED - per-rep link and the two flow-adherence columns. */
  showRepDetail?: boolean;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const rows = [
    [p.teamActivityAttempts, activityLabel(metrics.attempts, p.unavailable)],
    [p.teamActivityConnected, activityLabel(metrics.connected, p.unavailable)],
    [p.teamActivityMeetings, activityLabel(metrics.meetings, p.unavailable)],
  ] as const;
  const withFlows = reps.filter((rep) => rep.flows);
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
      <div className="sr-only">
      <table>
        <caption>{p.teamHeadingActivity}</caption>
        <thead>
          <tr>
            <th scope="col">{p.teamTableMetric}</th>
            <th scope="col">{p.teamTableValue}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {showRepDetail && withFlows.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">{p.teamRepFlowAdherenceHeading}</caption>
          <thead>
            <tr className="text-left">
              <th scope="col" className={THEME_TOKENS.typography.capsLabel}>{p.teamTableName}</th>
              <th scope="col" className={THEME_TOKENS.typography.capsLabel}>{p.teamRepFlowSdr}</th>
              <th scope="col" className={THEME_TOKENS.typography.capsLabel}>{p.teamRepFlowAe}</th>
            </tr>
          </thead>
          <tbody>
            {reps.map((rep) => (
              <tr key={rep.userId} className="border-t border-border/60">
                <th scope="row" className="py-1.5 text-left font-normal text-foreground">
                  <Link className="underline-offset-2 hover:underline" to={`/dashboard/insights/rep/${rep.userId}`}>
                    {rep.name}
                  </Link>
                </th>
                <td className="py-1.5">{repFlowAdherenceText(rep.flows?.sdr ?? null, p.teamRepFlowNoData)}</td>
                <td className="py-1.5">{repFlowAdherenceText(rep.flows?.ae ?? null, p.teamRepFlowNoData)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : reps.length > 0 ? (
        <p className={THEME_TOKENS.typography.body}>
          {reps.map((rep, index) => (
            <span key={rep.userId}>
              {index > 0 ? ", " : ""}
              {showRepDetail ? (
                <Link className="underline-offset-2 hover:underline" to={`/dashboard/insights/rep/${rep.userId}`}>
                  {rep.name}
                </Link>
              ) : (
                rep.name
              )}
            </span>
          ))}
        </p>
      ) : null}
    </section>
  );
}
