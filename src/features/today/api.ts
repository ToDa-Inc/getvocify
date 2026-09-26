import { REVIEW_LIMIT } from "@shared/ui/home.js";
import { api } from "@/shared/lib/api-client";
import type { PriorityView } from "@/lib/contact-priorities";
import type { DoneRow, FollowupRow, TodayView, UpcomingRow } from "@/lib/today";
import { memoKeys } from "@/features/memos/api";
import type { Memo } from "@/features/memos/types";

export const contactPriorityKeys = {
  all: ["contact-priorities"] as const,
  list: () => [...contactPriorityKeys.all, "list"] as const,
};

export const todayKeys = {
  all: ["today"] as const,
  view: () => [...todayKeys.all, "view"] as const,
};

export const homeKeys = {
  all: ["home"] as const,
  followups: () => [...homeKeys.all, "followups"] as const,
  upcoming: () => [...homeKeys.all, "upcoming"] as const,
  done: () => [...homeKeys.all, "done"] as const,
  reviews: () => [...memoKeys.lists(), "home-review"] as const,
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

export const homeApi = {
  followups: (): Promise<FollowupRow[]> => api.get<FollowupRow[]>("/followups?status=ready,generating,unavailable"),
  reviews: (): Promise<Memo[]> =>
    api.get<Memo[]>(`/memos?status=pending_review&reached_only=true&limit=${REVIEW_LIMIT}`),
  upcoming: (): Promise<UpcomingRow[]> => api.get<UpcomingRow[]>("/today/upcoming?days=7"),
  done: (): Promise<DoneRow[]> => api.get<DoneRow[]>("/today/done"),
};
