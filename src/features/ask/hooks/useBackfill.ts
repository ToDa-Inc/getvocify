import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/shared/lib/api-client";

type Coverage = { total: number; analysed: number; pending: number; running?: boolean; run_done?: number; queued?: number };
export type BackfillState =
  | { phase: "idle" }
  | { phase: "running"; done: number; total: number }
  | { phase: "done" }
  | { phase: "failed" };

const POLL_MS = 3000;

/** Ask the server to read the conversations it has not analysed yet, and follow its progress. */
export function useBackfill() {
  const [state, setState] = useState<BackfillState>({ phase: "idle" });
  const timer = useRef<number | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  const follow = useCallback(() => {
    const tick = async () => {
      if (!alive.current) return;
      try {
        const cov = await api.get<Coverage>("/intelligence/coverage");
        if (!alive.current) return;
        if (cov.running) {
          setState({ phase: "running", done: cov.run_done ?? 0, total: cov.queued ?? cov.pending });
          timer.current = window.setTimeout(tick, POLL_MS);
          return;
        }
        setState({ phase: "done" });
      } catch {
        if (alive.current) setState({ phase: "failed" });
      }
    };
    void tick();
  }, []);

  const start = useCallback(async () => {
    setState({ phase: "running", done: 0, total: 0 });
    try {
      const result = await api.post<{ started: boolean; reason?: string }>("/intelligence/backfill");
      if (!result.started && result.reason === "nothing_pending") {
        setState({ phase: "done" });
        return;
      }
      follow();
    } catch {
      setState({ phase: "failed" });
    }
  }, [follow]);

  /** How many conversations are really unread, overall: the number the confirmation should show. */
  const pending = useCallback(async (): Promise<number | null> => {
    try {
      return (await api.get<Coverage>("/intelligence/coverage")).pending;
    } catch {
      return null;
    }
  }, []);

  return { state, start, pending };
}
