import { api } from "@/shared/lib/api-client";
import type { UpcomingMeeting } from "@/lib/meeting-heads-up";

export type CalendarProvider = "google" | "microsoft";

export type CalendarConnection = {
  platform: "google_calendar" | "microsoft_outlook";
  email: string | null;
  status: "connecting" | "connected" | "disconnected";
  auto_join: boolean;
};

/** `providers`: the calendars this deployment can connect (OAuth app + Recall configured). */
export type CalendarState = {
  providers: CalendarProvider[];
  connection: CalendarConnection | null;
};

export const calendarKeys = {
  state: ["calendar"] as const,
};

export const calendarApi = {
  get: (): Promise<CalendarState> => api.get<CalendarState>("/calendar"),
  authorizeUrl: (provider: CalendarProvider): Promise<{ redirect_url: string }> =>
    api.get<{ redirect_url: string }>(`/calendar/${provider}/authorize`),
  setAutoJoin: (autoJoin: boolean): Promise<CalendarState> =>
    api.patch<CalendarState>("/calendar", { auto_join: autoJoin }),
  disconnect: (): Promise<void> => api.delete("/calendar"),
  /** The rep's next meetings with someone from outside, soonest first (empty without a calendar). */
  upcoming: (): Promise<UpcomingMeeting[]> => api.get<UpcomingMeeting[]>("/calendar/upcoming"),
};
