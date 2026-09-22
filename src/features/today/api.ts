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
};
