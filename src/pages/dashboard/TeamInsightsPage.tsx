import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
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
import { api } from "@/shared/lib/api-client";

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
      <main className="max-w-5xl mx-auto space-y-8 p-6">
        <h1>{t.product.teamTitle}</h1>
        <p>{query.isError ? t.product.teamReadFailed : t.product.teamLoading}</p>
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
    <main className="max-w-5xl mx-auto space-y-8 p-6">
      <h1>{t.product.teamTitle}</h1>
      {view.kind === "denied" ? <p>{view.title}</p> : null}
      {view.kind === "new" ? <p>{view.title}</p> : null}
      {allowed ? (
        <div className="flex flex-wrap gap-4">
          <label>
            {t.product.teamFilterRep}{" "}
            <select
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
          <label>
            {t.product.teamFilterMotion}{" "}
            <select
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
          <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>{t.product.teamResetFilters}</button>
        </div>
      ) : null}
      {view.kind === "ready" && view.metrics ? (
        <>
          <TeamOverview metrics={view.metrics} reps={view.reps} />
          <AdherenceBreakdown metrics={view.metrics} />
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
