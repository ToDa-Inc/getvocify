import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { HosFunnel, HosKpiTiles, HosOutcomesRow } from "@/features/head-of-sales/HosOverview";
import { currentTotals, useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import {
  HOS_DEFAULT_PERIOD,
  flowShortName,
  summaryDiagnosis,
  type HosPeriod,
  type HosSalesRole,
  type ProcessTone,
} from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { usesRepHome } from "@/lib/nav";
import { teamFlowFilterLabel } from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const TONE_DOT: Record<ProcessTone, string> = {
  process: "bg-warning",
  rep: "bg-beige",
  ok: "bg-success",
  neutral: "bg-muted-foreground/40",
};

/** Head of Sales /dashboard (plan §3.1): four numbers, one sentence, the funnel. Nothing to do today. */
export default function HeadOfSalesSummaryPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const query = useTeamAdherence(period, salesRole);
  const current = currentTotals(query.data);
  const diagnoses = summaryDiagnosis({
    attempts: query.data ? current.attempts : null,
    adherence: current.adherence,
    processHealth: query.data?.process_health ?? [],
  });
  const showRoles = Boolean(user?.company?.features?.includes("SALES_ROLES_ENABLED"));

  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="flex items-start justify-between gap-4">
        <HosPageHeader title={p.hosSummaryTitle} subtitle={p.hosSummarySubtitle} />
        {/* T13: a Head of Sales who also sells keeps a way to their own day, off the menu. */}
        {usesRepHome(user?.company) ? (
          <Link className="shrink-0 pt-2 text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground" to="/dashboard/today">
            {p.hosGoToToday}
          </Link>
        ) : null}
      </div>
      <HosFilters period={period} salesRole={salesRole} onPeriod={setPeriod} onSalesRole={setSalesRole} showRoles={showRoles} />
      {query.isError ? (
        <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>
      ) : query.isLoading ? (
        <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>
      ) : (
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
                          {diagnosis.href === "/dashboard/process" ? p.navProcess : p.hosSeeByPerson}
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
          <Link to="/dashboard/insights" className="inline-block text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground">
            {p.hosSeeByPerson}
          </Link>
        </div>
      )}
    </main>
  );
}
