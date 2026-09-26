import { api } from "@/shared/lib/api-client";

export type WritingSamples = { samples: string[] };

export const writingSampleKeys = {
  all: ["writing-samples"] as const,
  current: () => [...writingSampleKeys.all, "current"] as const,
};

export const writingSamplesApi = {
  get: (): Promise<WritingSamples> => api.get<WritingSamples>("/writing-samples"),
  put: (samples: string[]): Promise<WritingSamples> =>
    api.put<WritingSamples>("/writing-samples", { samples }),
};
