import { useCallback, useEffect, useState } from "react";
import { errorCode } from "@/features/playbooks/api";
import { assistantApi, isNotActivated, type Trial, type TrialRun, type Verdict } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";

type Settled = { kind: "judging" } | { kind: "after"; caseId: string; run: TrialRun | null; similar: { text: string; run: TrialRun } | null };
/**
 * Where the Head of Sales is in one case: deciding (judging), writing what they would say (`writing`, with where to go
 * back to), or looking at the new answer after a correction (`after`, with the similar phrase to check).
 */
export type TrialPhase = Settled | { kind: "writing"; mode: "say" | "never" | "branch"; caseId: string; situation?: string; back: Settled };

export type Activation = { state: "idle" | "working" | "done"; failed: string[] };

/**
 * The trial ("La prueba"): the company's open trial (or a new one), the run of the case on screen, and what is done with
 * a case: decide it, write a correction, look at the result, activate. Calls to the API never overlap (each waits for
 * the one before: the server keeps the trial as one piece), so the buttons are off while one is in flight.
 */
export function useTrial({ motionKey, onChanged }: { motionKey: string | null; onChanged: () => void }) {
  const { language } = useLanguage();
  const lang = language === "EN" ? "en" : "es";
  const [trial, setTrial] = useState<Trial | null>(null);
  const [load, setLoad] = useState<"loading" | "ready" | "error" | "not_activated">("loading");
  const [runs, setRuns] = useState<Record<string, TrialRun>>({});
  const [phase, setPhase] = useState<TrialPhase>({ kind: "judging" });
  const [deciding, setDeciding] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [activation, setActivation] = useState<Activation>({ state: "idle", failed: [] });
  const [retry, setRetry] = useState(0);

  const start = useCallback(
    async (fresh = false) => {
      setLoad("loading");
      setProblem(null);
      try {
        const next = await assistantApi.startTrial({ ...(motionKey ? { motion_key: motionKey } : {}), lang, ...(fresh ? { fresh: true } : {}) });
        setTrial(next);
        setRuns(next.runs);
        setPhase({ kind: "judging" });
        setShowResult(false);
        setActivation({ state: "idle", failed: [] });
        setLoad("ready");
      } catch (error) {
        setLoad(isNotActivated(error) ? "not_activated" : "error");
      }
    },
    [motionKey, lang],
  );

  useEffect(() => {
    void start();
  }, [start]);

  // The case on screen: the one being decided, written about or just corrected.
  const caseId = phase.kind === "judging" ? (trial?.current_id ?? null) : phase.caseId;
  const run = caseId ? (runs[caseId] ?? null) : null;

  // Its run, when it has none yet.
  useEffect(() => {
    if (!trial || !caseId || runs[caseId] || phase.kind === "after") return;
    let cancelled = false;
    assistantApi
      .runCase(trial.id, caseId)
      .then((done) => !cancelled && setRuns((now) => ({ ...now, [caseId]: done.run })))
      .catch((error) => !cancelled && setProblem(errorCode(error) ?? "unknown"));
    return () => {
      cancelled = true;
    };
  }, [trial, caseId, runs, phase.kind, retry]);

  const finished = Boolean(trial) && (showResult || (trial?.current_id === null && phase.kind === "judging"));

  /** Records what was decided. True when it was recorded (the field can be emptied). */
  const decide = async (verdict: Verdict, text?: string, when?: string): Promise<boolean> => {
    if (!trial || !caseId) return false;
    setDeciding(true);
    setProblem(null);
    try {
      const done = await assistantApi.decide(trial.id, caseId, { verdict, ...(text ? { text } : {}), ...(when ? { when } : {}) });
      setTrial(done.trial);
      if (done.run) setRuns((now) => ({ ...now, [caseId]: done.run as TrialRun }));
      if (verdict === "approve" || verdict === "unknown") setPhase({ kind: "judging" });
      else {
        setPhase({ kind: "after", caseId, run: done.run, similar: verdict === "corrected" ? done.similar : null });
        onChanged();
      }
      return true;
    } catch (error) {
      setProblem(errorCode(error) ?? "unknown");
      return false;
    } finally {
      setDeciding(false);
    }
  };

  const write = (mode: "say" | "never") => {
    if (caseId && phase.kind === "judging") setPhase({ kind: "writing", mode, caseId, back: phase });
  };
  const writeBranch = () => {
    if (phase.kind === "after" && phase.similar) setPhase({ kind: "writing", mode: "branch", caseId: phase.caseId, situation: phase.similar.text, back: phase });
  };
  const cancelWriting = () => {
    if (phase.kind === "writing") {
      setProblem(null);
      setPhase(phase.back);
    }
  };
  const next = () => setPhase({ kind: "judging" });

  const activate = async () => {
    if (!trial) return;
    setActivation({ state: "working", failed: [] });
    try {
      const done = await assistantApi.activateTrial(trial.id);
      setActivation({ state: "done", failed: done.failed.map((item) => item.key) });
      onChanged();
    } catch (error) {
      setActivation({ state: "idle", failed: [] });
      setProblem(errorCode(error) ?? "unknown");
    }
  };

  return {
    status: load,
    trial,
    caseId,
    run,
    phase,
    deciding,
    problem,
    finished,
    activation,
    decide,
    write,
    writeBranch,
    cancelWriting,
    next,
    activate,
    finish: () => setShowResult(true),
    resume: () => setShowResult(false),
    again: () => start(true),
    reload: () => start(),
    retryRun: () => {
      setProblem(null);
      setRetry((now) => now + 1);
    },
  };
}

export type TrialController = ReturnType<typeof useTrial>;
