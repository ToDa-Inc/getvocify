import type { ReactNode } from "react";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { adherenceBarRatio, type TeamMetrics } from "@/lib/team-insights";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`;

export function AdherenceBreakdown({ metrics, children }: { metrics: TeamMetrics; children?: ReactNode }) {
  const { t } = useLanguage();
  const p = t.product;
  const label =
    metrics.adherence === null
      ? p.teamAdherenceEmpty
      : p.teamAdherenceOf.replace("{met}", String(metrics.met)).replace("{applicable}", String(metrics.applicable));
  const barRatio = adherenceBarRatio(metrics);
  return (
    <section aria-labelledby="team-adherence" className={card}>
      <h2 id="team-adherence" className={THEME_TOKENS.typography.sectionTitle}>{p.teamHeadingAdherence}</h2>
      <p>{label}</p>
      {barRatio !== null ? (
        <div className="relative h-4 w-full max-w-md overflow-hidden rounded-full bg-secondary">
          <div className="h-full bg-primary" style={{ width: `${barRatio * 100}%` }} />
        </div>
      ) : null}
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className={THEME_TOKENS.typography.capsLabel}>{p.teamAdherenceMet}</dt>
          <dd className="text-foreground">{metrics.met}</dd>
        </div>
        <div>
          <dt className={THEME_TOKENS.typography.capsLabel}>{p.teamAdherenceApplicable}</dt>
          <dd className="text-foreground">{metrics.applicable}</dd>
        </div>
      </dl>
      <div className="sr-only">
      <table>
        <caption>{p.teamHeadingAdherence}</caption>
        <thead>
          <tr>
            <th scope="col">{p.teamTableMetric}</th>
            <th scope="col">{p.teamTableValue}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">{p.teamAdherenceMet}</th>
            <td>{metrics.met}</td>
          </tr>
          <tr>
            <th scope="row">{p.teamAdherenceApplicable}</th>
            <td>{metrics.applicable}</td>
          </tr>
        </tbody>
      </table>
      </div>
      {metrics.sampleLimited ? (
        <p>{p.sampleLimited}</p>
      ) : null}
      {children}
    </section>
  );
}
