import { useEffect, useRef, useState } from "react";
import {
  answerCard,
  assistContext,
  BACKSTOP_MS,
  checkPath,
  checkStamps,
  checkTiming,
  draftCard,
  nextStep,
  PAUSE_MS,
  previousAnswers,
  lineLevels,
  prospectSilent,
  skipAnswered,
  turnCheck,
  type AssistCard,
  type AssistContext,
} from "@/lib/live-assist";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";
import { getDesktopBridge } from "@/lib/desktop-host";
import { ASSIST_SOURCES, readTurn } from "./sources";

/** An answer later than this is no use: the rep has said the filler and moved on. The card stays. */
const ANSWER_MS = 5000;

/** One line in the Mac's live-help log (a test switch on the Mac turns it on). */
function note(name: string, details: Record<string, unknown> = {}) {
  getDesktopBridge()?.shell.log?.(name, details);
}

/**
 * Whether the prospect has paused: true once their side has been quiet for PAUSE_MS, false while
 * they speak, null until their audio has been heard at all (then live help reads only the words).
 */
function useProspectPause(level: number | undefined) {
  const heardRef = useRef(false);
  /** When their audio last went quiet (null while they speak or before it was heard): for the event log. */
  const quietSinceRef = useRef<number | null>(null);
  const levelRef = useRef<number | null>(null);
  const floorRef = useRef<number | null>(null);
  const [paused, setPaused] = useState(false);
  // Their line's own noise: a real microphone or a phone line is never digital silence, so quiet is measured from it.
  const readingsRef = useRef<{ t: number; level: number }[]>([]);
  const now = Date.now();
  if (level !== undefined) {
    readingsRef.current.push({ t: now, level });
    if (readingsRef.current.length > 200) readingsRef.current.splice(0, readingsRef.current.length - 200);
  }
  // A steady level does not change, so nothing re-renders: a once-a-second tick keeps the floor current.
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const line = lineLevels(readingsRef.current, now);
  floorRef.current = line?.floor ?? null;
  levelRef.current = level ?? null;
  const silent = level === undefined || prospectSilent(level, line);
  if (!silent) heardRef.current = true;
  useEffect(() => {
    setPaused(false);
    quietSinceRef.current = silent && heardRef.current ? Date.now() : null;
    if (!silent) return;
    // Logged to time their last word against the card: when their level drops, and when it counts as a pause.
    if (heardRef.current) note("quiet");
    const timer = window.setTimeout(() => {
      setPaused(true);
      if (heardRef.current) note("pause");
    }, PAUSE_MS);
    return () => window.clearTimeout(timer);
  }, [silent]);
  return { paused: heardRef.current ? paused && silent : null, quietSinceRef, levelRef, floorRef };
}

/**
 * Live help, with turn detection. When the prospect pauses, one fast check says whether they
 * finished and which objection it is: the card (label and a filler line to say at once) shows
 * right then, and its answer is written for that type and lands below the filler line, whole.
 */
export type LiveAssistCall = {
  contactId?: string | null;
  /** From the platform that caught the call. */
  callMode?: "softphone" | "meeting";
  /** The call's type: help uses that playbook. */
  typeKey?: string | null;
  /** Their side's audio level (0–1): when it goes quiet is when they may have finished. */
  prospectLevel?: number;
};

type Found = NonNullable<ReturnType<typeof assistContext>>;

export function useLiveAssist(turns: MeetingDisplayTurn[], enabled: boolean, call: LiveAssistCall = {}) {
  const [active, setActive] = useState<AssistCard | null>(null);
  const [thinking, setThinking] = useState(false);
  const { paused, quietSinceRef, levelRef, floorRef } = useProspectPause(call.prospectLevel);
  /** When their words last changed (the transcript revising counts), to time a check against it. */
  const changedAtRef = useRef(0);
  /** The words last checked: the same words are never checked twice. */
  const lastKeyRef = useRef("");
  /** How much of their current turn help already handled: the next check is about what came after. */
  const askedRef = useRef<{ turnKey: string; length: number } | null>(null);
  const checkRef = useRef<AbortController | null>(null);
  const answerRef = useRef<AbortController | null>(null);
  const backstopRef = useRef<number | undefined>(undefined);
  /** Every card shown in this call, oldest first: so answers never repeat. */
  const shownRef = useRef<AssistCard[]>([]);
  /** When the newest card appeared: no new check starts until its cooldown is over. */
  const shownAtRef = useRef<number | null>(null);
  /** The conversation as of the latest render, for a check that waited and must see what was said meanwhile. */
  const turnsRef = useRef(turns);
  turnsRef.current = turns;

  const found = enabled ? assistContext(turns, askedRef.current) : null;
  const context = found
    ? {
        ...found,
        ...(call.contactId && { contactId: call.contactId }),
        ...(call.callMode && { callMode: call.callMode }),
        ...(call.typeKey && { typeKey: call.typeKey }),
      }
    : null;
  const key = context?.key ?? "";

  /** Shows a new card; it replaces the one up (past cards are not kept on screen). */
  const present = (card: AssistCard) => {
    // A card's first appearance starts its cooldown; the answer landing in it later does not restart it.
    if (!shownRef.current.some((item) => item.id === card.id)) shownAtRef.current = Date.now();
    const shown = shownRef.current;
    shownRef.current = shown.some((item) => item.id === card.id)
      ? shown.map((item) => (item.id === card.id ? card : item))
      : [...shown, card];
    setActive(card);
  };

  /** Writes the answer. With a type, its card is already up; without one, the stream names it. */
  const answer = (ctx: AssistContext, type: string | null, since: number, entry?: { entryId?: string; label?: string }) => {
    const controller = new AbortController();
    answerRef.current = controller;
    setThinking(true);
    let draft: AssistCard | null = null;
    if (type) {
      draft = draftCard(type, ctx.latestTurn, Date.now(), entry?.label);
      note("draft", { label: draft.label, bridge: draft.bridge, ms: Date.now() - since });
      present(draft);
    }
    const onDraft = (card: AssistCard) => {
      if (controller.signal.aborted || draft) return;
      note("draft", { label: card.label, bridge: card.bridge, ms: Date.now() - since });
      draft = card;
      present(card);
    };
    // The answer is written for the type on screen, as the next sentence after its filler line.
    // It also carries the lines already shown in this call (not this card's): the new one must differ.
    const previous = previousAnswers(shownRef.current.filter((card) => card.id !== draft?.id));
    const told = previous.length ? { ...ctx, previousAnswers: previous } : ctx;
    const asked =
      type && draft
        ? { ...told, objectionType: type, filler: draft.bridge, ...(entry?.entryId && { entryId: entry.entryId }) }
        : told;
    let done = false;
    const finish = (results: (AssistCard | null)[], late = false) => {
      if (done || controller.signal.aborted) return;
      done = true;
      window.clearTimeout(limit);
      setThinking(false);
      const now = Date.now();
      const card = results.find(Boolean) ?? null;
      if (!card) note(late ? "answer-late" : "silent", { label: draft?.label ?? null, ms: now - since });
      // No answer never takes a card away: its label and filler line stay, the dots stop.
      const shown = answerCard(draft, card);
      if (!shown) return;
      if (card) {
        note("answer", { label: shown.label, sayThis: shown.sayThis, ms: now - since });
      }
      present(shown);
    };
    const limit = window.setTimeout(() => finish([], true), ANSWER_MS);
    void Promise.all(ASSIST_SOURCES.map((source) => source.request(asked, controller.signal, onDraft))).then((results) =>
      finish(results),
    );
  };

  /** One turn check on their words. final: they have been quiet long enough that "still going" means done. */
  const check = (
    ctx: AssistContext & Found,
    final: boolean,
    how: { path: ReturnType<typeof checkPath> | "backstop"; waitMs: number; deferred: boolean },
  ) => {
    lastKeyRef.current = ctx.key;
    checkRef.current?.abort();
    const controller = new AbortController();
    checkRef.current = controller;
    const since = Date.now();
    // Every check, even one newer words replace: shows how long after they stop the check starts.
    note("check", { latest: ctx.latestTurn, final });
    // What the client saw as this check started, for the event log: where the time went.
    const stamps = checkStamps({
      path: how.path,
      now: since,
      quietSince: quietSinceRef.current,
      changedAt: changedAtRef.current,
      waitMs: how.waitMs,
      deferred: how.deferred,
      final,
      level: levelRef.current,
      floor: floorRef.current,
    });
    void readTurn(ctx, controller.signal, stamps).then((reading) => {
      if (controller.signal.aborted) return;
      const step = nextStep(reading, final);
      note("turn", { latest: ctx.latestTurn, ...reading, final, step: step.do, ms: Date.now() - since });
      if (step.do === "wait") {
        backstopRef.current = window.setTimeout(
          () => check(ctx, true, { path: "backstop", waitMs: BACKSTOP_MS, deferred: false }),
          BACKSTOP_MS,
        );
        return;
      }
      // These words are handled: the next check is about what they say after.
      askedRef.current = { turnKey: ctx.turnKey, length: ctx.length };
      if (step.do === "skip") return;
      answer(ctx, step.do === "answer" ? step.type : null, since, step.do === "answer" ? step : undefined);
    });
  };

  // Every change in their words (the transcript revising counts) is stamped, to time a check against it.
  useEffect(() => {
    changedAtRef.current = Date.now();
  }, [key]);

  useEffect(() => {
    // While an answer is written nothing new starts: its card is on screen and must not be replaced.
    if (!context || thinking || key === lastKeyRef.current) return;
    const plan = turnCheck({ settled: found!.settled, paused });
    // While a card is being read, wait; the words stay unhandled, so the check after it reads what they say by then.
    const { waitMs, deferred } = checkTiming({ afterMs: plan.afterMs, shownAt: shownAtRef.current, now: Date.now() });
    const timer = window.setTimeout(() => {
      // A check that waited is skipped when the rep has answered meanwhile: its card would answer the past.
      if (skipAnswered(deferred, turnsRef.current, context.turnKey)) {
        note("skip-answered", { latest: context.latestTurn });
        lastKeyRef.current = context.key;
        askedRef.current = { turnKey: context.turnKey, length: context.length };
        return;
      }
      check(context, plan.final, { path: checkPath(paused, found!.settled), waitMs, deferred });
    }, waitMs);
    return () => window.clearTimeout(timer);
    // The key captures every change in their words; context is derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, paused, thinking]);

  // New words replace a backstop set for older ones.
  useEffect(() => () => window.clearTimeout(backstopRef.current), [key]);

  useEffect(() => {
    if (enabled) return;
    checkRef.current?.abort();
    answerRef.current?.abort();
    window.clearTimeout(backstopRef.current);
    setThinking(false);
    setActive(null);
    shownRef.current = [];
    shownAtRef.current = null;
  }, [enabled]);

  useEffect(
    () => () => {
      checkRef.current?.abort();
      answerRef.current?.abort();
      window.clearTimeout(backstopRef.current);
    },
    [],
  );

  return { active, thinking };
}

const ENABLED_KEY = "vocify_live_assist_on";

function readEnabled(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) !== "0";
  } catch {
    return true;
  }
}

/** On unless the rep turned it off; remembered per Mac. It stays silent until there is something to say. */
export function useLiveAssistEnabled() {
  const [enabled, setEnabled] = useState(readEnabled);
  const toggle = (next: boolean) => {
    setEnabled(next);
    try {
      localStorage.setItem(ENABLED_KEY, next ? "1" : "0");
    } catch {
      /* per-viewer convenience only */
    }
  };
  return [enabled, toggle] as const;
}
