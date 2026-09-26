import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
import { AdherenceTrend } from "@/features/team-insights/components/AdherenceTrend";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { OutcomeBreakdown } from "@/features/team-insights/components/OutcomeBreakdown";
import { TeamOverview } from "@/features/team-insights/components/TeamOverview";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  teamAdherenceHasData,
  teamCrmCoverage,
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

function adherenceQuery(filters: TeamFilters): string {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.motion) params.set("motion", filters.motion);
  const qs = params.toString();
  return qs ? `/team/adherence?${qs}` : "/team/adherence";
}

export default function TeamInsightsPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const role = user?.company?.role ?? "member";
  const [filters, setFilters] = useState<TeamFilters>(EMPTY_FILTERS);
  const allowed = role === "owner" || role === "admin";
  const query = useQuery({
    queryKey: ["team-adherence", filters],
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
        reps?: TeamRep[];
        review?: { memo_id: string; line: string }[];
      }>(adherenceQuery(filters)),
    enabled: allowed,
    retry: false,
  });
  const motionsQuery = useQuery({
    queryKey: ["playbook-motions"],
    queryFn: () => api.get<{ motions: Record<string, string> }>("/playbooks"),
    enabled: allowed,
    retry: false,
  });
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
                  {motionLabel(key, t.product.motions)}
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
          <TeamOverview metrics={view.metrics} reps={view.reps} />
          <AdherenceBreakdown metrics={view.metrics}>
            <AdherenceTrend filters={filters} />
          </AdherenceBreakdown>
          <ObjectionBreakdown categories={query.data?.objection_categories ?? []} />
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
