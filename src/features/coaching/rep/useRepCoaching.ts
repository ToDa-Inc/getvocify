import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { CoachCalls } from "@/lib/rep-coaching";

/** The Coaching tab for one interaction type; null lets the backend pick the rep's main one. */
export function useCoachCalls(type: string | null) {
  return useQuery({
    queryKey: ["rep-coaching", "calls", type ?? "auto"],
    queryFn: () => api.get<CoachCalls>(`/coaching/me/calls${type ? `?type=${encodeURIComponent(type)}` : ""}`),
    retry: false,
    placeholderData: (previous) => previous,
  });
}
