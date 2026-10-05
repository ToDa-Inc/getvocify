import { useEffect, useRef, useState } from "react";
import {
  addCard,
  answerCard,
  assistContext,
  BACKSTOP_MS,
  cooldownKey,
  coolingDown,
  draftCard,
  nextStep,
  PAUSE_MS,
  prospectSilent,
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
function useProspectPause(level: number | undefined): boolean | null {
  const heardRef = useRef(false);
  const [paused, setPaused] = useState(false);
  const silent = level === undefined || prospectSilent(level);
  if (!silent) heardRef.current = true;
  useEffect(() => {
    setPaused(false);
    if (!silent) return;
    const timer = window.setTimeout(() => setPaused(true), PAUSE_MS);
    return () => window.clearTimeout(timer);
  }, [silent]);
  return heardRef.current ? paused && silent : null;
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
  const [earlier, setEarlier] = useState<AssistCard[]>([]);
  const [thinking, setThinking] = useState(false);
  const paused = useProspectPause(call.prospectLevel);
  /** The words last checked: the same words are never checked twice. */
  const lastKeyRef = useRef("");
  /** How much of their current turn help already handled: the next check is about what came after. */
  const askedRef = useRef<{ turnKey: string; length: number } | null>(null);
  const checkRef = useRef<AbortController | null>(null);
  const answerRef = useRef<AbortController | null>(null);
  const backstopRef = useRef<number | undefined>(undefined);
  const lastShownRef = useRef<Record<string, number>>({});

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

  /** Shows a new card, moving whatever was up into "Earlier". */
  const present = (card: AssistCard) => {
    setActive((current) => {
      if (current && current.id !== card.id && current.stage === "ready") setEarlier((list) => addCard(list, current));
      return card;
    });
  };

  /** Writes the answer. With a type, its card is already up; without one, the stream names it. */
  const answer = (ctx: AssistContext, type: string | null, since: number) => {
    const controller = new AbortController();
    answerRef.current = controller;
    setThinking(true);
    let draft: AssistCard | null = null;
    if (type) {
      draft = draftCard(type, ctx.latestTurn, Date.now());
      if (coolingDown(draft, lastShownRef.current, Date.now())) {
        note("draft-cooling", { label: draft.label, ms: Date.now() - since });
        setThinking(false);
        return;
      }
      note("draft", { label: draft.label, bridge: draft.bridge, ms: Date.now() - since });
      present(draft);
    }
    const onDraft = (card: AssistCard) => {
      if (controller.signal.aborted || draft) return;
      if (coolingDown(card, lastShownRef.current, Date.now())) {
        note("draft-cooling", { label: card.label, ms: Date.now() - since });
        return;
      }
      note("draft", { label: card.label, bridge: card.bridge, ms: Date.now() - since });
      draft = card;
      present(card);
    };
    const asked = { ...ctx, ...(type && { objectionType: type }) };
    let done = false;
    const finish = (results: (AssistCard | null)[], late = false) => {
      if (done || controller.signal.aborted) return;
      done = true;
      window.clearTimeout(limit);
      setThinking(false);
      const now = Date.now();
      const card = results.find((result) => result && (draft || !coolingDown(result, lastShownRef.current, now))) ?? null;
      if (!card) {
        const cooling = results.find(Boolean);
        note(late ? "answer-late" : cooling ? "answer-cooling" : "silent", { label: draft?.label ?? cooling?.label ?? null, ms: now - since });
      }
      // No answer never takes a card away: its label and filler line stay, the dots stop.
      const shown = answerCard(draft, card);
      if (!shown) return;
      if (card) {
        lastShownRef.current[cooldownKey(shown)] = shown.at;
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
  const check = (ctx: AssistContext & Found, final: boolean) => {
    lastKeyRef.current = ctx.key;
    checkRef.current?.abort();
    const controller = new AbortController();
    checkRef.current = controller;
    const since = Date.now();
    void readTurn(ctx, controller.signal).then((reading) => {
      if (controller.signal.aborted) return;
      const step = nextStep(reading, final);
      note("turn", { latest: ctx.latestTurn, ...reading, final, step: step.do, ms: Date.now() - since });
      if (step.do === "wait") {
        backstopRef.current = window.setTimeout(() => check(ctx, true), BACKSTOP_MS);
        return;
      }
      // These words are handled: the next check is about what they say after.
      askedRef.current = { turnKey: ctx.turnKey, length: ctx.length };
      if (step.do === "skip") return;
      answer(ctx, step.do === "answer" ? step.type : null, since);
    });
  };

  useEffect(() => {
    // While an answer is written nothing new starts: its card is on screen and must not be replaced.
    if (!context || thinking || key === lastKeyRef.current) return;
    const plan = turnCheck({ settled: found!.settled, paused });
    const timer = window.setTimeout(() => check(context, plan.final), plan.afterMs);
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
  }, [enabled]);

  useEffect(
    () => () => {
      checkRef.current?.abort();
      answerRef.current?.abort();
      window.clearTimeout(backstopRef.current);
    },
    [],
  );

  return { active, earlier, thinking };
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
