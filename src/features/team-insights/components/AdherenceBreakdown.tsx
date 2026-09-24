import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { adherenceBarRatio, type TeamMetrics } from "@/lib/team-insights";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`;

export function AdherenceBreakdown({ metrics }: { metrics: TeamMetrics }) {
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
      {metrics.sampleLimited ? (
        <p>{p.sampleLimited}</p>
      ) : null}
    </section>
  );
}
