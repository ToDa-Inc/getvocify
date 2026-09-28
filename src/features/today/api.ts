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
  resolve: (id: string, body: { action: string; request_id: string; expected_version: number; until?: string }) =>
    api.post<{ id: string; status: string; version: number; undo_deadline: string | null }>(`/today/${id}/resolve`, body),
  /** Persists an id-less never-contacted card so it can be acted on (idempotent per contact). */
  persistNeverContacted: (body: { contact_id: string; connection_id?: string }) =>
    api.post<{ id: string; status: string; version: number; undo_deadline: string | null }>("/today/never-contacted", body),
  undo: (id: string, body: { request_id: string; expected_version: number }) =>
    api.patch<{ id: string; status: string; version: number; undo_deadline: string | null }>(`/today/${id}`, body),
};

export type HandoffRequest = {
  contact_id: string;
  connection_id?: string;
  deal_id?: string | null;
  ae_user_id?: string | null;
  memo_id?: string | null;
  meeting_starts_at?: string | null;
};

export type HandoffResult = {
  id: string | null;
  status: string | null;
  ae_user_id?: string | null;
  created: boolean;
  crm_owner_status: string | null;
};

export const handoffsApi = {
  create: (body: HandoffRequest): Promise<HandoffResult> => api.post<HandoffResult>("/handoffs", body),
  /** "cancelled": undo / give back to the SDR. "closed": the deal is done (AE or Head of Sales). */
  close: (id: string, reason: "cancelled" | "closed") =>
    api.post<{ id: string; status: string; changed: boolean }>(`/handoffs/${encodeURIComponent(id)}/close`, { reason }),
};

export const homeApi = {
  followups: (): Promise<FollowupRow[]> => api.get<FollowupRow[]>("/followups?status=ready,generating,unavailable"),
  reviews: (): Promise<Memo[]> =>
    api.get<Memo[]>(`/memos?status=pending_review&reached_only=true&limit=${REVIEW_LIMIT}`),
  upcoming: (): Promise<UpcomingRow[]> => api.get<UpcomingRow[]>("/today/upcoming?days=7"),
  done: (): Promise<DoneRow[]> => api.get<DoneRow[]>("/today/done"),
};
