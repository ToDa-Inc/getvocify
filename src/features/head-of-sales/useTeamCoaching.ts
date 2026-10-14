import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { HosPeriod, HosSalesRole } from "@/lib/head-of-sales";
import type { TeamCoaching } from "@/lib/team-coaching";

/** Equipo for one period, position and interaction type; null type lets the backend pick the main one. */
export function useTeamCoaching(period: HosPeriod, salesRole: HosSalesRole, type: string | null) {
  const params = new URLSearchParams({ period });
  if (salesRole !== "all") params.set("sales_role", salesRole);
  if (type) params.set("type", type);
  return useQuery({
    queryKey: ["team-coaching", period, salesRole, type ?? "auto"],
    queryFn: () => api.get<TeamCoaching>(`/team/coaching?${params.toString()}`),
    retry: false,
    placeholderData: (previous) => previous,
  });
}
