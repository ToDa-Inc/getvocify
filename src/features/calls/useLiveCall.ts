import { useCallback, useEffect, useState } from "react";

import { resolveApiBase } from "@/lib/app-url";
import { followLiveCalls, type LiveState } from "@/lib/live-call";
import { api } from "@/shared/lib/api-client";

const EMPTY: LiveState = { call: null };

/**
 * The rep's live call, kept in sync over /live-calls/stream.
 *
 * start() at call start with the CRM pages on screen (the Mac app reads them
 * with the `crm:pages` bridge op) and, to record it, a client capture id: the
 * contact is the record on screen and the capture memo is reserved with it.
 * When call.needs_contact is true (deal/company page, list, nothing open), ask
 * the rep and send the answer with pickContact(). end() at hang-up; the
 * capture itself completes through /captures/{id}/complete.
 */
export function useLiveCall(enabled = true) {
  const [state, setState] = useState<LiveState>(EMPTY);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void followLiveCalls({
      url: `${resolveApiBase()}/live-calls/stream`,
      getToken: () => api.getToken(),
      onState: setState,
      onConnectedChange: setConnected,
      signal: controller.signal,
    });
    return () => {
      controller.abort();
      setConnected(false);
    };
  }, [enabled]);

  const start = useCallback(async (pageUrls: string[], clientCaptureId?: string) => {
    const next = await api.post<LiveState>("/live-calls/start", {
      page_urls: pageUrls,
      client_capture_id: clientCaptureId,
      started_at: new Date().toISOString(),
    });
    setState(next);
    return next;
  }, []);

  const pickContact = useCallback(async (provider: "hubspot" | "pipedrive", contactId: string) => {
    const next = await api.patch<LiveState>("/live-calls/current", { provider, contact_id: contactId });
    setState(next);
    return next;
  }, []);

  const end = useCallback(async () => {
    const next = await api.post<LiveState>("/live-calls/current/end");
    setState(next);
    return next;
  }, []);

  return { ...state, connected, start, pickContact, end };
}
