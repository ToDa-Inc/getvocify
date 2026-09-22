/** Team insights. Names are alphabetical. A meeting is not a win, and an empty filter is not a zero. */

import type { ProductTranslations } from "./product-catalog";

export type TeamRep = { userId: string; name: string };

export type TeamFilters = { period: string; motion: string | null; userId: string | null };

export type TeamDeal = {
  dealId: string;
  status: "won" | "lost" | "open";
  attribution: "assigned" | "unresolved";
  ownerUserId: string | null;
};

export type ObjectionCategory = {
  name: string;
  count: number;
  resolved: number;
  open: number;
  unknown: number;
};

export type ObjectionResolutionLabels = Pick<
  ProductTranslations,
  "resolutionResolved" | "resolutionOpen" | "resolutionUnknown"
>;

export function objectionResolutionCountsText(
  item: Pick<ObjectionCategory, "resolved" | "open" | "unknown">,
  labels: ObjectionResolutionLabels,
): string {
  return `${labels.resolutionResolved} ${item.resolved} ${labels.resolutionOpen} ${item.open} ${labels.resolutionUnknown} ${item.unknown}`;
}

export type ObjectionCatalog = Record<string, string>;

/** Drop zero counts; map stable category keys through the catalog; other names pass through. */
export function objectionDisplayName(name: string, catalog: ObjectionCatalog): string {
  const key = name.trim().toLowerCase();
  return catalog[key] ?? name;
}

export function visibleObjectionCategories(
  categories: ObjectionCategory[],
  catalog: ObjectionCatalog,
): ObjectionCategory[] {
  return categories
    .filter((item) => item.count > 0)
    .map((item) => ({
      name: objectionDisplayName(item.name, catalog),
      count: item.count,
      resolved: item.resolved,
      open: item.open,
      unknown: item.unknown,
    }))
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      return a.name.localeCompare(b.name, "es");
    });
}

export function objectionCategoriesEmptyMessage(
  categories: ObjectionCategory[],
  catalog: ObjectionCatalog,
  emptyWeek: string,
): string | null {
  return visibleObjectionCategories(categories, catalog).length === 0 ? emptyWeek : null;
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
  sampleLimited: boolean;
};

export type TeamInsightsCopy = Pick<
  ProductTranslations,
  | "teamDenied"
  | "teamNewPanel"
  | "teamNoDataForFilters"
  | "teamUnresolvedAttribution"
>;

/** CRM win-loss coverage comes only from explicit crm_coverage on the payload. */
export function teamCrmCoverage(crmCoverage: unknown): TeamMetrics["coverageCrm"] {
  if (crmCoverage === "complete") return "complete";
  if (crmCoverage === "partial") return "partial";
  return "unavailable";
}

/** Share of steps met when adherence is defined and applicable > 0; otherwise no bar. */
export function adherenceBarRatio(metrics: Pick<TeamMetrics, "adherence" | "met" | "applicable">): number | null {
  if (metrics.adherence === null || metrics.applicable <= 0) return null;
  return metrics.met / metrics.applicable;
}

export function activityLabel(value: number | null, unavailable: string): string {
  return value === null ? unavailable : String(value);
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
  copy: TeamInsightsCopy;
}): {
  kind: "denied" | "new" | "empty" | "ready";
  title?: string;
  reps: TeamRep[];
  winRate: number | null;
  partialCrmWarning: boolean;
  unresolvedLabel: string;
  metrics: TeamMetrics | null;
} {
  const reps = repsByName(input.reps);
  const { copy } = input;
  if (input.role !== "owner" && input.role !== "admin") {
    return {
      kind: "denied",
      title: copy.teamDenied,
      reps: [],
      winRate: null,
      partialCrmWarning: false,
      unresolvedLabel: copy.teamUnresolvedAttribution,
      metrics: null,
    };
  }
  if (input.companyEmpty) {
    return {
      kind: "new",
      title: copy.teamNewPanel,
      reps,
      winRate: null,
      partialCrmWarning: false,
      unresolvedLabel: copy.teamUnresolvedAttribution,
      metrics: null,
    };
  }
  if (!input.metrics) {
    return {
      kind: "empty",
      title: copy.teamNoDataForFilters,
      reps,
      winRate: null,
      partialCrmWarning: false,
      unresolvedLabel: copy.teamUnresolvedAttribution,
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
    partialCrmWarning: input.metrics.coverageCrm !== "complete",
    unresolvedLabel: copy.teamUnresolvedAttribution,
    metrics: input.metrics,
  };
}
