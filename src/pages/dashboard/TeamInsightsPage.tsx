import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { OutcomeBreakdown } from "@/features/team-insights/components/OutcomeBreakdown";
import { teamInsightsView, type TeamFilters, type TeamMetrics } from "@/lib/team-insights";
import { api } from "@/shared/lib/api-client";

const EMPTY_FILTERS: TeamFilters = { period: "week", motion: null, userId: null };

export default function TeamInsightsPage() {
  const { user } = useAuth();
  const role = user?.company?.role ?? "member";
  const [filters, setFilters] = useState<TeamFilters>(EMPTY_FILTERS);
  const allowed = role === "owner" || role === "admin";
  const query = useQuery({
    queryKey: ["team-adherence", filters],
    queryFn: () => api.get<{ adherence: number | null; met_steps: number; applicable_steps: number; coverage: number | null }>("/team/adherence"),
    enabled: allowed,
    retry: false,
  });
  if (allowed && (query.isLoading || query.isError)) {
    return (
      <main className="max-w-5xl mx-auto space-y-8 p-6">
        <h1>Equipo</h1>
        <p>{query.isError ? "No se pudo leer el equipo" : "Leyendo…"}</p>
      </main>
    );
  }
  const metrics: TeamMetrics | null = query.data
    ? {
        attempts: null,
        connected: null,
        meetings: null,
        won: null,
        lost: null,
        unresolvedWins: 0,
        adherence: query.data.adherence,
        met: query.data.met_steps,
        applicable: query.data.applicable_steps,
        coverageCrm: query.data.coverage === null ? "unavailable" : "complete",
      }
    : null;
  const view = teamInsightsView({
    role,
    companyEmpty: false,
    filters,
    reps: [],
    metrics: query.isSuccess ? metrics : null,
  });

  return (
    <main className="max-w-5xl mx-auto space-y-8 p-6">
      <h1>Equipo</h1>
      {view.kind === "denied" ? <p>{view.title}</p> : null}
      {view.kind === "new" ? <p>{view.title}</p> : null}
      {view.kind === "empty" ? (
        <div>
          <p>{view.title}</p>
          <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>Restablecer filtros</button>
        </div>
      ) : null}
      {view.kind === "ready" && view.metrics ? (
        <>
          <AdherenceBreakdown metrics={view.metrics} />
          <ObjectionBreakdown categories={[]} />
          <OutcomeBreakdown
            metrics={view.metrics}
            winRate={view.winRate}
            unresolvedLabel={view.unresolvedLabel}
            partialWarning={view.partialWarning}
          />
        </>
      ) : null}
    </main>
  );
}
