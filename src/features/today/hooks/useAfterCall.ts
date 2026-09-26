import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { callsApi } from "@/features/calls/api";
import { afterCallPoll, afterCallResolution, type CallSummary } from "@/lib/after-call";
import type { CallResolvedEvent } from "@/lib/today-queue";

/**
 * Reads the call the rep just hung up until its memo is processed (bounded, home cadence).
 * If processing shows there was no conversation or the call failed, hands that back once.
 */
export function useAfterCall(
  callSid: string | null,
  active: boolean,
  onResolved: (event: CallResolvedEvent) => void,
): CallSummary | undefined {
  const sinceRef = useRef<{ sid: string | null; at: number | null }>({ sid: null, at: null });
  const query = useQuery({
    queryKey: ["home-after-call", callSid],
    queryFn: () => callsApi.getCall(callSid as string),
    enabled: Boolean(active && callSid),
    retry: false,
    refetchInterval: (q) => {
      const since = sinceRef.current.sid === callSid ? sinceRef.current.at : null;
      const next = afterCallPoll(q.state.data, since, Date.now());
      sinceRef.current = { sid: callSid, at: next.since };
      return next.interval;
    },
  });

  const resolution = active ? afterCallResolution(query.data) : null;
  const resolvedRef = useRef(onResolved);
  resolvedRef.current = onResolved;
  useEffect(() => {
    if (resolution) resolvedRef.current({ outcome: resolution, callSid });
  }, [resolution, callSid]);

  return active ? query.data : undefined;
}
