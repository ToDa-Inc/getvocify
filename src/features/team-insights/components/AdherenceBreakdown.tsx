import { useLanguage } from "@/lib/i18n";
import { adherenceBarRatio, type TeamMetrics } from "@/lib/team-insights";

export function AdherenceBreakdown({ metrics }: { metrics: TeamMetrics }) {
  const { t } = useLanguage();
  const p = t.product;
  const label =
    metrics.adherence === null
      ? p.teamAdherenceEmpty
      : p.teamAdherenceOf.replace("{met}", String(metrics.met)).replace("{applicable}", String(metrics.applicable));
  const barRatio = adherenceBarRatio(metrics);
  return (
    <section aria-labelledby="team-adherence">
      <h2 id="team-adherence">{p.teamHeadingAdherence}</h2>
      <p>{label}</p>
      {barRatio !== null ? (
        <div className="relative h-4 w-full max-w-md overflow-hidden rounded-full bg-secondary">
          <div className="h-full bg-primary" style={{ width: `${barRatio * 100}%` }} />
        </div>
      ) : null}
      <table>
        <tbody>
          <tr><th>{p.teamAdherenceMet}</th><td>{metrics.met}</td></tr>
          <tr><th>{p.teamAdherenceApplicable}</th><td>{metrics.applicable}</td></tr>
        </tbody>
      </table>
      {metrics.sampleLimited ? (
        <p>{p.sampleLimited}</p>
      ) : null}
    </section>
  );
}
