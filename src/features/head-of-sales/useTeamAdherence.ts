import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { CompetitorMention, ObjectionCategory } from "@/lib/team-insights";
import {
  adherenceParams,
  type HosPeriod,
  type HosRep,
  type HosSalesRole,
  type ProcessHealthFlow,
} from "@/lib/head-of-sales";

export type HosTotals = { attempts: number; connected: number; meetings: number; adherence: number | null };

export type HosAdherence = {
  attempts?: number;
  connected?: number;
  meetings?: number;
  adherence: number | null;
  sample_limited?: boolean;
  previous?: HosTotals;
  reps?: HosRep[];
  /** Present when the CRM reported outcomes; null/absent = no outcomes. */
  won?: number | null;
  lost?: number | null;
  crm_coverage?: "complete" | "partial" | "unavailable";
  process_health?: ProcessHealthFlow[];
  objection_categories?: ObjectionCategory[];
  competitor_mentions?: CompetitorMention[];
};

/** The Head of Sales pages all read /team/adherence with period + sales_role (one producer). */
export function useTeamAdherence(period: HosPeriod, salesRole: HosSalesRole, options: { withFocus?: boolean } = {}) {
  const withFocus = options.withFocus === true;
  return useQuery({
    // The focus variant is a different (heavier) response: its own cache entry.
    queryKey: withFocus
      ? ["hos-team-adherence", period, salesRole, "focus"]
      : ["hos-team-adherence", period, salesRole],
    queryFn: () =>
      api.get<HosAdherence>(
        `/team/adherence?${adherenceParams({ manager: true, period, salesRole, userId: null, motion: null, withFocus })}`,
      ),
    retry: false,
    placeholderData: (previous) => previous,
  });
}

export function currentTotals(data: HosAdherence | undefined): HosTotals {
  return {
    attempts: data?.attempts ?? 0,
    connected: data?.connected ?? 0,
    meetings: data?.meetings ?? 0,
    adherence: data?.adherence ?? null,
  };
}
