import { useEffect, useState } from "react";

import { resolveApiBase } from "@/lib/app-url";
import { followLiveCalls, type LiveCall } from "@/lib/live-call";
import { api } from "@/shared/lib/api-client";

/**
 * The rep's current call, as reported by the Chrome extension from HubSpot,
 * with the contact already resolved. `call` stays set after hang-up (status
 * "ended"/"completed") until the backend drops it or the next call starts.
 */
export function useLiveCall(enabled = true): { call: LiveCall | null; connected: boolean } {
  const [call, setCall] = useState<LiveCall | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void followLiveCalls({
      url: `${resolveApiBase()}/live-calls/stream`,
      getToken: () => api.getToken(),
      onCall: setCall,
      onConnectedChange: setConnected,
      signal: controller.signal,
    });
    return () => {
      controller.abort();
      setConnected(false);
    };
  }, [enabled]);

  return { call, connected };
}
