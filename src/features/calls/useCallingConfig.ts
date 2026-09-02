import { useCallback, useEffect, useState } from "react";
import { callsApi } from "@/features/calls/api";
import type { CallingConfig } from "@/features/calls/types";

export function useCallingConfig() {
  const [config, setConfig] = useState<CallingConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const reload = useCallback(async () => {
    const next = await callsApi.getConfig();
    setConfig(next);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await callsApi.getConfig();
        if (!cancelled) setConfig(next);
      } catch (error) {
        console.error("Failed to load calling config", error);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { config, isLoading, reload };
}
