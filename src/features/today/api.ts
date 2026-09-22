import { api } from "@/shared/lib/api-client";
import type { PriorityView } from "@/lib/contact-priorities";

export const contactPriorityKeys = {
  all: ["contact-priorities"] as const,
  list: () => [...contactPriorityKeys.all, "list"] as const,
};

export const contactPrioritiesApi = {
  list: (): Promise<PriorityView> => api.get<PriorityView>("/contact-priorities"),
};
