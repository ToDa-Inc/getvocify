import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
import { AdherenceTrend } from "@/features/team-insights/components/AdherenceTrend";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { OutcomeBreakdown } from "@/features/team-insights/components/OutcomeBreakdown";
import { TeamOverview } from "@/features/team-insights/components/TeamOverview";
import { ManagerOverview } from "@/features/team-insights/components/ManagerOverview";
import { ProcessHealth } from "@/features/team-insights/components/ProcessHealth";
import {
  HOS_PERIODS,
  adherenceParams,
  type HosPeriod,
  type HosRep,
  type HosSalesRole,
  type ProcessHealthFlow,
} from "@/lib/head-of-sales";
import { isManagerRole } from "@/lib/nav";
import { useLanguage } from "@/lib/i18n";
import {
  teamAdherenceHasData,
  teamCrmCoverage,
  teamFlowFilterLabel,
  teamInsightsView,
  type ObjectionCategory,
  type TeamFilters,
  type TeamMetrics,
  type TeamRep,
} from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

const field = "mt-1 block w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground";

const EMPTY_FILTERS: TeamFilters = { period: "week", motion: null, userId: null };

// Head of Sales phase 2: a manager also sends period and sales_role; a member with
// visibility=team sends exactly what it sent before (adherenceParams).
function adherenceQuery(filters: TeamFilters, manager: boolean, salesRole: HosSalesRole): string {
  const qs = adherenceParams({
    manager,
    period: filters.period as HosPeriod,
    salesRole,
    userId: filters.userId,
    motion: filters.motion,
  });
  return qs ? `/team/adherence?${qs}` : "/team/adherence";
}

type PhaseTwoTotals = { attempts: number; connected: number; meetings: number; adherence: number | null };

const ROLE_FILTERS: { value: HosSalesRole; key: "hosRoleAll" | "hosRoleSdr" | "hosRoleAe" }[] = [
  { value: "all", key: "hosRoleAll" },
  { value: "sdr", key: "hosRoleSdr" },
  { value: "ae", key: "hosRoleAe" },
];

export default function TeamInsightsPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const role = user?.company?.role ?? "member";
  const [filters, setFilters] = useState<TeamFilters>(EMPTY_FILTERS);
  const manager = isManagerRole(role);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  // T1/D3: a member with visibility=team also reads this page (read-only) - the backend
  // is the source of truth (403 otherwise), this only decides whether to fire the query.
  const allowed = role === "owner" || role === "admin" || user?.company?.visibility === "team";
  const managerHomeEnabled = Boolean(user?.company?.features?.includes("MANAGER_HOME_ENABLED"));
  const query = useQuery({
    queryKey: ["team-adherence", filters, manager ? salesRole : null],
    queryFn: () =>
      api.get<{
        adherence: number | null;
        met_steps: number;
        applicable_steps: number;
        coverage: number | null;
        crm_coverage?: "complete" | "partial";
        won?: number | null;
        lost?: number | null;
        unresolved_wins?: number;
        sample_limited?: boolean;
        attempts?: number;
        connected?: number;
        meetings?: number;
        objection_categories?: ObjectionCategory[];
        competitor_mentions?: { name: string; count: number; quotes?: { quote: string; date: string }[] }[];
        reps?: TeamRep[];
        review?: { memo_id: string; line: string }[];
        previous?: PhaseTwoTotals;
        process_health?: ProcessHealthFlow[];
      }>(adherenceQuery(filters, manager, salesRole)),
    enabled: allowed,
    retry: false,
  });
  const motionsQuery = useQuery({
    queryKey: ["playbook-motions"],
    queryFn: () => api.get<{ motions: Record<string, string> }>("/playbooks"),
    enabled: allowed,
    retry: false,
  });
  // Lista 4 E5: a rep who can't read the team panel has Coach instead of Team.
  if (user && !allowed) return <Navigate to="/dashboard/coach" replace />;
  if (allowed && (query.isLoading || query.isError)) {
    return (
      <main className={`max-w-5xl mx-auto space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product.teamTitle}</h1>
        <p className={THEME_TOKENS.typography.body}>{query.isError ? t.product.teamReadFailed : t.product.teamLoading}</p>
      </main>
    );
  }
  const reps: TeamRep[] = query.data?.reps ?? [];
  const filterActive = Boolean(filters.userId || filters.motion);
  const scopedEmpty = filterActive && query.data != null && !teamAdherenceHasData(query.data);
  const metrics: TeamMetrics | null =
    query.data && !scopedEmpty
      ? {
          attempts: typeof query.data.attempts === "number" ? query.data.attempts : null,
          connected: typeof query.data.connected === "number" ? query.data.connected : null,
          meetings: typeof query.data.meetings === "number" ? query.data.meetings : null,
          won: query.data.won ?? null,
          lost: query.data.lost ?? null,
          unresolvedWins: query.data.unresolved_wins ?? 0,
          adherence: query.data.adherence,
          met: query.data.met_steps,
          applicable: query.data.applicable_steps,
          coverageCrm: teamCrmCoverage(query.data.crm_coverage),
          sampleLimited: query.data.sample_limited === true,
        }
      : null;
  const view = teamInsightsView({
    role,
    visibility: user?.company?.visibility,
    companyEmpty: false,
    filters,
    reps,
    metrics: query.isSuccess ? metrics : null,
    copy: t.product,
  });
  const motionKeys = Object.keys(motionsQuery.data?.motions ?? {}).sort((a, b) =>
    a.localeCompare(b, "es"),
  );

  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <h1 className={THEME_TOKENS.typography.pageTitle}>{t.product.teamTitle}</h1>
      {view.kind === "denied" ? <p>{view.title}</p> : null}
      {view.kind === "new" ? <p>{view.title}</p> : null}
      {manager ? (
        <div className="flex flex-wrap items-end gap-3" data-testid="hos-filters">
          <label className={THEME_TOKENS.typography.capsLabel}>
            {t.product.hosPeriodLabel}
            <select
              className={field}
              value={filters.period}
              onChange={(event) => setFilters((prev) => ({ ...prev, period: event.target.value }))}
            >
              {HOS_PERIODS.map((option) => (
                <option key={option.value} value={option.value}>
                  {String(t.product[option.labelKey])}
                </option>
              ))}
            </select>
          </label>
          <div role="group" aria-label={t.product.hosRoleLabel} className="inline-flex rounded-full border border-border bg-card p-1">
            {ROLE_FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={salesRole === option.value}
                onClick={() => {
                  setSalesRole(option.value);
                  setFilters((prev) => ({ ...prev, userId: null }));
                }}
                className={`rounded-full px-3.5 py-1 text-xs transition-colors ${
                  salesRole === option.value ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t.product[option.key]}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {allowed ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className={THEME_TOKENS.typography.capsLabel}>
            {t.product.teamFilterRep}
            <select
              className={field}
              value={filters.userId ?? ""}
              onChange={(event) =>
                setFilters((prev) => ({
                  ...prev,
                  userId: event.target.value ? event.target.value : null,
                }))
              }
            >
              <option value="">{t.product.teamFilterAllReps}</option>
              {reps.map((rep) => (
                <option key={rep.userId} value={rep.userId}>
                  {rep.name}
                </option>
              ))}
            </select>
          </label>
          <label className={THEME_TOKENS.typography.capsLabel}>
            {t.product.teamFilterMotion}
            <select
              className={field}
              value={filters.motion ?? ""}
              onChange={(event) =>
                setFilters((prev) => ({
                  ...prev,
                  motion: event.target.value ? event.target.value : null,
                }))
              }
            >
              <option value="">{t.product.teamFilterAllMotions}</option>
              {motionKeys.map((key) => (
                <option key={key} value={key}>
                  {teamFlowFilterLabel(key, t.product, t.product.motions)}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      {view.kind === "empty" ? (
        <div>
          <p>{view.title}</p>
          <button type="button" className="mt-3 rounded-full border border-border px-3 py-1.5 text-sm" onClick={() => setFilters(EMPTY_FILTERS)}>{t.product.teamResetFilters}</button>
        </div>
      ) : null}
      {view.kind === "ready" && view.metrics ? (
        <>
          {(query.data?.review?.length ?? 0) > 0 ? (
            <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 p-5`}>
              <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.teamReviewTitle}</h2>
              <ul className="space-y-2">
                {query.data?.review?.map((item) => (
                  <li key={item.memo_id}>
                    <Link className="text-[15px] leading-relaxed text-foreground" to={`/dashboard/memos/${item.memo_id}`}>
                      {item.line}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {manager ? (
            <>
              <ManagerOverview
                current={{
                  attempts: view.metrics.attempts,
                  connected: view.metrics.connected,
                  meetings: view.metrics.meetings,
                  adherence: view.metrics.adherence,
                }}
                previous={query.data?.previous ?? null}
                reps={(query.data?.reps ?? []) as HosRep[]}
                showRepDetail={managerHomeEnabled}
                csvName={`team-${filters.period}.csv`}
              />
              <ProcessHealth flows={query.data?.process_health ?? []} playbookHref="/dashboard/settings/playbooks" />
            </>
          ) : (
            <TeamOverview metrics={view.metrics} reps={view.reps} showRepDetail={managerHomeEnabled} />
          )}
          <AdherenceBreakdown metrics={view.metrics}>
            <AdherenceTrend filters={filters} />
          </AdherenceBreakdown>
          <ObjectionBreakdown
            categories={query.data?.objection_categories ?? []}
            competitors={query.data?.competitor_mentions}
            sampleLimited={query.data?.sample_limited === true}
            emptyText={manager && filters.period !== "week" ? t.product.hosObjectionsEmptyPeriod : undefined}
          />
          <OutcomeBreakdown
            metrics={view.metrics}
            winRate={view.winRate}
            unresolvedLabel={view.unresolvedLabel}
            partialWarning={view.partialCrmWarning ? t.product.partialCrm : null}
          />
        </>
      ) : null}
    </main>
  );
}
