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
  process_health?: ProcessHealthFlow[];
  objection_categories?: ObjectionCategory[];
  competitor_mentions?: CompetitorMention[];
};

/** The Head of Sales pages all read /team/adherence with period + sales_role (one producer). */
export function useTeamAdherence(period: HosPeriod, salesRole: HosSalesRole) {
  return useQuery({
    queryKey: ["hos-team-adherence", period, salesRole],
    queryFn: () =>
      api.get<HosAdherence>(
        `/team/adherence?${adherenceParams({ manager: true, period, salesRole, userId: null, motion: null })}`,
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
