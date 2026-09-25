import { api } from "@/shared/lib/api-client";
import type { PriorityView } from "@/lib/contact-priorities";
import type { TodayView } from "@/lib/today";

export const contactPriorityKeys = {
  all: ["contact-priorities"] as const,
  list: () => [...contactPriorityKeys.all, "list"] as const,
};

export const todayKeys = {
  all: ["today"] as const,
  view: () => [...todayKeys.all, "view"] as const,
};

export const contactPrioritiesApi = {
  list: (): Promise<PriorityView> => api.get<PriorityView>("/contact-priorities"),
};

export const todayApi = {
  get: (): Promise<TodayView> => api.get<TodayView>("/today"),
  resolve: (id: string, body: { action: string; request_id: string; expected_version: number }) =>
    api.post<{ id: string; status: string; version: number; undo_deadline: string | null }>(`/today/${id}/resolve`, body),
  undo: (id: string, body: { request_id: string; expected_version: number }) =>
    api.patch<{ id: string; status: string; version: number; undo_deadline: string | null }>(`/today/${id}`, body),
};
