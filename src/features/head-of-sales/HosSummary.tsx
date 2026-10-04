import { Link } from "react-router-dom";
import { HosFunnel, HosKpiTiles, HosOutcomesRow } from "@/features/head-of-sales/HosOverview";
import { currentTotals, useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import {
  PROCESS_HREF,
  flowShortName,
  summaryDiagnosis,
  type HosPeriod,
  type HosSalesRole,
  type ProcessTone,
} from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { teamFlowFilterLabel } from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const TONE_DOT: Record<ProcessTone, string> = {
  process: "bg-warning",
  rep: "bg-beige",
  ok: "bg-success",
  neutral: "bg-muted-foreground/40",
};

/** Equipo → Resumen (plan §3.1): one sentence on people vs process, four numbers, outcomes, the funnel. */
export function HosSummary({ period, salesRole }: { period: HosPeriod; salesRole: HosSalesRole }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useTeamAdherence(period, salesRole);
  const current = currentTotals(query.data);
  const diagnoses = summaryDiagnosis({
    attempts: query.data ? current.attempts : null,
    adherence: current.adherence,
    processHealth: query.data?.process_health ?? [],
  });

  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>;
  if (query.isLoading) return <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>;
  return (
    <div className={`space-y-6 transition-opacity ${query.isPlaceholderData ? "opacity-50" : ""}`} aria-busy={query.isPlaceholderData}>
      <div
        className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 p-5 text-[15px] leading-relaxed text-foreground`}
        data-testid="hos-diagnosis"
      >
        {diagnoses.map((diagnosis) => {
          const flow = diagnosis.motion
            ? flowShortName(diagnosis.motion, teamFlowFilterLabel(diagnosis.motion, p, p.motions))
            : "";
          return (
            <p key={`${diagnosis.key}-${diagnosis.motion ?? ""}`} className="flex items-start gap-3">
              <span className={`mt-2 h-2 w-2 shrink-0 rounded-full ${TONE_DOT[diagnosis.tone]}`} aria-hidden />
              <span>
                {p[diagnosis.key].replace("{flow}", flow)}
                {diagnosis.href ? (
                  <>
                    {" "}
                    <Link className="text-muted-foreground underline underline-offset-2 hover:text-foreground" to={diagnosis.href}>
                      {diagnosis.href === PROCESS_HREF ? p.settingsNavPlaybooks : p.hosSeeByPerson}
                    </Link>
                  </>
                ) : null}
              </span>
            </p>
          );
        })}
      </div>
      <HosKpiTiles current={current} previous={query.data?.previous ?? null} />
      <HosOutcomesRow
        won={query.data?.won}
        lost={query.data?.lost}
        crmCoverage={query.data?.crm_coverage}
        sampleLimited={query.data?.sample_limited === true}
      />
      <HosFunnel current={current} />
    </div>
  );
}
