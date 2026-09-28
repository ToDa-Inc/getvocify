import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import {
  interactionsQuery,
  type CoachExamples,
  type CoachInteractions,
  type CoachProcess,
  type CoachSummary,
  type InteractionFilters,
} from "@/lib/rep-coaching";

export function useCoachSummary() {
  return useQuery({
    queryKey: ["rep-coaching", "summary"],
    queryFn: () => api.get<CoachSummary>("/coaching/me/summary"),
    retry: false,
  });
}

export function useCoachInteractions(filters: InteractionFilters) {
  return useQuery({
    queryKey: ["rep-coaching", "interactions", filters.stepId, filters.state, filters.meetingOnly],
    queryFn: () => api.get<CoachInteractions>(`/coaching/me/interactions?${interactionsQuery(filters)}`),
    retry: false,
    placeholderData: (previous) => previous,
  });
}

export function useCoachProcess(weeks = 8) {
  return useQuery({
    queryKey: ["rep-coaching", "process", weeks],
    queryFn: () => api.get<CoachProcess>(`/coaching/me/process?weeks=${weeks}`),
    retry: false,
  });
}

export function useCoachExamples() {
  return useQuery({
    queryKey: ["rep-coaching", "examples"],
    queryFn: () => api.get<CoachExamples>("/coaching/examples"),
    retry: false,
  });
}
