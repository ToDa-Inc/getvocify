import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import {
  interactionsQuery,
  type CoachExamples,
  type CoachFlow,
  type CoachInteractions,
  type CoachProcess,
  type CoachSummary,
  type InteractionFilters,
} from "@/lib/rep-coaching";

// `flow` is only sent when a general rep picked one; the backend ignores it for SDR/AE and
// resolves a default otherwise. It is part of every key so switching never shows the other flow.
const flowParam = (flow: CoachFlow | null | undefined, joiner: "?" | "&") => (flow ? `${joiner}flow=${flow}` : "");

export function useCoachSummary(flow?: CoachFlow | null) {
  return useQuery({
    queryKey: ["rep-coaching", "summary", flow ?? "auto"],
    queryFn: () => api.get<CoachSummary>(`/coaching/me/summary${flowParam(flow, "?")}`),
    retry: false,
  });
}

export function useCoachInteractions(filters: InteractionFilters, flow?: CoachFlow | null) {
  return useQuery({
    queryKey: ["rep-coaching", "interactions", flow ?? "auto", filters.stepId, filters.state, filters.meetingOnly],
    queryFn: () => api.get<CoachInteractions>(`/coaching/me/interactions?${interactionsQuery(filters, flow)}`),
    retry: false,
    placeholderData: (previous) => previous,
  });
}

export function useCoachProcess(flow?: CoachFlow | null, weeks = 8) {
  return useQuery({
    queryKey: ["rep-coaching", "process", flow ?? "auto", weeks],
    queryFn: () => api.get<CoachProcess>(`/coaching/me/process?weeks=${weeks}${flowParam(flow, "&")}`),
    retry: false,
  });
}

export function useCoachExamples(flow?: CoachFlow | null) {
  return useQuery({
    queryKey: ["rep-coaching", "examples", flow ?? "auto"],
    queryFn: () => api.get<CoachExamples>(`/coaching/examples${flowParam(flow, "?")}`),
    retry: false,
  });
}
