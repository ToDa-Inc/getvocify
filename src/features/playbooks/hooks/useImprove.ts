import { useCallback, useEffect, useState } from "react";
import { errorCode } from "@/features/playbooks/api";
import { assistantApi, isNotActivated, type ImproveQueue, type ImproveStats, type QueueActionKind } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";

export type ImproveStatus = "loading" | "ready" | "error" | "not_activated";
export type Publication = { state: "idle" | "working" | "done"; failed: string[] };
/** The code of the last failure and the case it belongs to (null: the screen as a whole). */
export type ImproveProblem = { code: string; at: string | null };

/**
 * "Mejoras con el uso": the numbers (coverage always, the success rate when it is switched on) and the queue of answers
 * that keep failing. Judging calls happens only when the Head of Sales presses "Actualizar" (a bounded batch, apart from
 * the post-call process). Calls to the API never overlap, so the buttons are off while one is in flight; `problem` is the
 * code of the last failure for the screen to word, and whatever was typed stays in its field until an action is saved.
 */
export function useImprove({ onChanged }: { onChanged: () => void }) {
  const { language } = useLanguage();
  const lang = language === "EN" ? "en" : "es";
  const [stats, setStats] = useState<ImproveStats | null>(null);
  const [queue, setQueue] = useState<ImproveQueue | null>(null);
  const [status, setStatus] = useState<ImproveStatus>("loading");
  const [refreshing, setRefreshing] = useState(false);
  const [note, setNote] = useState<{ judged: number; queued: number } | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  const [problem, setProblem] = useState<ImproveProblem | null>(null);
  const [publication, setPublication] = useState<Publication>({ state: "idle", failed: [] });

  /** Reads the numbers and the queue again; `quiet` keeps what is on screen instead of showing the skeleton. */
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setStatus("loading");
    try {
      const next = await assistantApi.improveStats();
      setStats(next);
      setQueue(next.success ? await assistantApi.improveQueue() : null);
      setStatus("ready");
    } catch (error) {
      if (!quiet || isNotActivated(error)) setStatus(isNotActivated(error) ? "not_activated" : "error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const busy = refreshing || acting !== null || publication.state === "working";

  const refresh = async () => {
    if (busy) return;
    setRefreshing(true);
    setProblem(null);
    try {
      setNote(await assistantApi.improveRefresh());
      await load(true);
    } catch (error) {
      setProblem({ code: errorCode(error) ?? "unknown", at: null });
    } finally {
      setRefreshing(false);
    }
  };

  /** Does `action` on one case. True when it was done (the field can be emptied). Anything but "keep" changed the draft. */
  const act = async (momentId: string, action: QueueActionKind, text?: string): Promise<boolean> => {
    if (busy) return false;
    setActing(momentId);
    setProblem(null);
    try {
      const done = await assistantApi.improveAct(momentId, { action, ...(text ? { text } : {}), lang });
      setQueue(done.queue);
      setPublication((now) => (action === "keep" ? now : { state: "idle", failed: [] }));
      void load(true);
      if (action !== "keep") onChanged();
      return true;
    } catch (error) {
      setProblem({ code: errorCode(error) ?? "unknown", at: momentId });
      return false;
    } finally {
      setActing(null);
    }
  };

  /** The Head of Sales says whether the suggestion settled it, whatever the judge decided. */
  const correctVerdict = async (momentId: string, eventId: string, resolved: "resolved" | "not_resolved") => {
    if (busy) return;
    setActing(momentId);
    setProblem(null);
    try {
      await assistantApi.improveVerdict(eventId, resolved);
      await load(true);
    } catch (error) {
      setProblem({ code: errorCode(error) ?? "unknown", at: momentId });
    } finally {
      setActing(null);
    }
  };

  const publish = async () => {
    if (busy) return;
    setPublication({ state: "working", failed: [] });
    setProblem(null);
    try {
      const done = await assistantApi.improvePublish();
      setPublication({ state: "done", failed: done.failed.map((item) => item.key) });
      await load(true);
      onChanged();
    } catch (error) {
      setPublication({ state: "idle", failed: [] });
      setProblem({ code: errorCode(error) ?? "unknown", at: null });
    }
  };

  return { status, stats, queue, refreshing, note, acting, problem, publication, refresh, act, correctVerdict, publish, reload: () => load(), clearProblem: () => setProblem(null) };
}

export type ImproveController = ReturnType<typeof useImprove>;
