import { api } from "@/shared/lib/api-client";

export type BriefHighlightMode = "immediate" | "deferred" | "end_of_day";

export type BriefPreference = {
  highlight_mode: BriefHighlightMode;
  delay_minutes: number | null;
  end_of_day: string | null;
  timezone: string;
};

export const briefPreferenceKeys = {
  all: ["brief-preferences"] as const,
  current: () => [...briefPreferenceKeys.all, "current"] as const,
};

export const briefPreferencesApi = {
  get: (): Promise<BriefPreference> => api.get<BriefPreference>("/brief-preferences"),
  put: (body: Pick<BriefPreference, "highlight_mode">): Promise<BriefPreference> =>
    api.put<BriefPreference>("/brief-preferences", body),
};
