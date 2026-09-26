import { api } from "@/shared/lib/api-client";
import type { NotificationsResponse, ReportSnapshot } from "@/lib/report-snapshot";

/** Only the reports that apply to this person come back; an absent key is not offered. */
export type ReportPreferences = Partial<Record<"daily" | "weekly" | "team", boolean>>;

export type StoredReport = {
  id: string;
  revision: number;
  scope: "self" | "team";
  period_start: string;
  report_type: "daily" | "weekly";
  snapshot: ReportSnapshot;
};

export const reportKeys = {
  notifications: ["notifications"] as const,
  report: (id: string | undefined) => ["report", id] as const,
  preferences: ["report-preferences"] as const,
};

export const reportsApi = {
  get: (id: string): Promise<StoredReport> => api.get<StoredReport>(`/reports/${id}`),
  notifications: (): Promise<NotificationsResponse> => api.get<NotificationsResponse>("/notifications"),
  markRead: (notificationId: string): Promise<{ id: string; read_at: string | null }> =>
    api.patch<{ id: string; read_at: string | null }>(`/notifications/${encodeURIComponent(notificationId)}`, {}),
  preferences: (): Promise<ReportPreferences> => api.get<ReportPreferences>("/me/report-preferences"),
  savePreferences: (changes: ReportPreferences): Promise<ReportPreferences> =>
    api.put<ReportPreferences>("/me/report-preferences", changes),
};
