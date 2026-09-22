/** Team insights. Names are alphabetical. A meeting is not a win, and an empty filter is not a zero. */

export type TeamRep = { userId: string; name: string };

export type TeamFilters = { period: string; motion: string | null; userId: string | null };

export type TeamDeal = {
  dealId: string;
  status: "won" | "lost" | "open";
  attribution: "assigned" | "unresolved";
  ownerUserId: string | null;
};

export type ObjectionCategory = { name: string; count: number };

const RAW_OBJECTION_KEYS = new Set([
  "price",
  "timing",
  "authority",
  "competitor",
  "status_quo",
  "trust",
  "other",
]);

/** Spanish labels from the API; drop zero counts and raw category keys. */
export function visibleObjectionCategories(categories: ObjectionCategory[]): ObjectionCategory[] {
  return categories
    .filter((item) => item.count > 0)
    .filter((item) => !RAW_OBJECTION_KEYS.has(item.name.trim().toLowerCase()))
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      return a.name.localeCompare(b.name, "es");
    });
}

export function objectionCategoriesEmptyMessage(categories: ObjectionCategory[]): string | null {
  return visibleObjectionCategories(categories).length === 0 ? "No hay objeciones esta semana." : null;
}

export type TeamMetrics = {
  attempts: number | null;
  connected: number | null;
  meetings: number | null;
  won: number | null;
  lost: number | null;
  unresolvedWins: number;
  adherence: number | null;
  met: number;
  applicable: number;
  coverageCrm: "complete" | "partial" | "unavailable";
};

/** Share of steps met when adherence is defined and applicable > 0; otherwise no bar. */
export function adherenceBarRatio(metrics: Pick<TeamMetrics, "adherence" | "met" | "applicable">): number | null {
  if (metrics.adherence === null || metrics.applicable <= 0) return null;
  return metrics.met / metrics.applicable;
}

export function activityLabel(value: number | null): string {
  return value === null ? "No disponible" : String(value);
}

/** True when adherence payload has memos/scores/objections in the filtered scope. */
export function teamAdherenceHasData(data: {
  attempts?: number;
  met_steps?: number;
  objection_categories?: ObjectionCategory[];
}): boolean {
  if ((data.attempts ?? 0) > 0) return true;
  if ((data.met_steps ?? 0) > 0) return true;
  return (data.objection_categories ?? []).some((item) => item.count > 0);
}

export function repsByName(reps: TeamRep[]): TeamRep[] {
  return [...reps].sort((a, b) => a.name.localeCompare(b.name, "es"));
}

export function winsForFilter(deals: TeamDeal[], userId: string | null): TeamDeal[] {
  const won = deals.filter((deal) => deal.status === "won");
  if (!userId) return won;
  return won.filter((deal) => deal.attribution === "assigned" && deal.ownerUserId === userId);
}

export function teamInsightsView(input: {
  role: string;
  companyEmpty: boolean;
  filters: TeamFilters;
  reps: TeamRep[];
  metrics: TeamMetrics | null;
}): {
  kind: "denied" | "new" | "empty" | "ready";
  title?: string;
  reps: TeamRep[];
  winRate: number | null;
  partialWarning: string | null;
  unresolvedLabel: string;
  metrics: TeamMetrics | null;
} {
  const reps = repsByName(input.reps);
  if (input.role !== "owner" && input.role !== "admin") {
    return { kind: "denied", title: "No puedes ver el equipo", reps: [], winRate: null, partialWarning: null, unresolvedLabel: "Sin atribución resuelta", metrics: null };
  }
  if (input.companyEmpty) {
    return {
      kind: "new",
      title: "El panel se completará con las interacciones de tu equipo",
      reps,
      winRate: null,
      partialWarning: null,
      unresolvedLabel: "Sin atribución resuelta",
      metrics: null,
    };
  }
  if (!input.metrics) {
    return {
      kind: "empty",
      title: "No hay datos para estos filtros",
      reps,
      winRate: null,
      partialWarning: null,
      unresolvedLabel: "Sin atribución resuelta",
      metrics: null,
    };
  }
  const known = (input.metrics.won ?? 0) + (input.metrics.lost ?? 0);
  const winRate = input.metrics.coverageCrm === "complete" && known > 0 && input.metrics.won !== null
    ? input.metrics.won / known
    : null;
  return {
    kind: "ready",
    reps,
    winRate,
    partialWarning: input.metrics.coverageCrm === "complete" ? null : "Falta parte de los cierres del CRM",
    unresolvedLabel: "Sin atribución resuelta",
    metrics: input.metrics,
  };
}
