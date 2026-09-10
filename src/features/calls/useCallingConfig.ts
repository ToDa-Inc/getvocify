import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { callKeys, callsApi } from "@/features/calls/api";
import { SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import type { CallingConfig } from "@/features/calls/types";

export function useCallingConfig() {
  const queryClient = useQueryClient();
  const { data: config = null, isLoading } = useQuery({
    queryKey: callKeys.config(),
    queryFn: () => callsApi.getConfig(),
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const reload = useCallback(async () => {
    const next = await callsApi.getConfig();
    queryClient.setQueryData(callKeys.config(), next);
    return next;
  }, [queryClient]);

  const setConfig = useCallback(
    (updater: CallingConfig | ((prev: CallingConfig | null) => CallingConfig | null)) => {
      queryClient.setQueryData<CallingConfig | null>(callKeys.config(), (prev) =>
        typeof updater === "function" ? updater(prev ?? null) : updater,
      );
    },
    [queryClient],
  );

  return { config, isLoading, reload, setConfig };
}
