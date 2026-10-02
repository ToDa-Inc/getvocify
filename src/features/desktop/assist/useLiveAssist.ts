import { useEffect, useRef, useState } from "react";
import {
  addCard,
  askAfterMs,
  assistContext,
  cooldownKey,
  coolingDown,
  type AssistCard,
} from "@/lib/live-assist";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";
import { getDesktopBridge } from "@/lib/desktop-host";
import { ASSIST_SOURCES } from "./sources";

/** One line in the Mac's live-help log (a test switch on the Mac turns it on). */
function note(name: string, details: Record<string, unknown> = {}) {
  getDesktopBridge()?.shell.log?.(name, details);
}

/** Never ask more often than this, so help never chases every word. */
const MIN_GAP_MS = 3000;

/**
 * Asks the assist sources after the other side pauses. As soon as a source knows
 * help is coming, a draft with a bridge line shows; the answer replaces it in place.
 * Display rules live in lib/live-assist (8–25s, stays while the rep answers).
 */
export type LiveAssistCall = {
  contactId?: string | null;
  /** From the platform that caught the call. */
  callMode?: "softphone" | "meeting";
  /** The call's type: help uses that playbook. */
  typeKey?: string | null;
};

export function useLiveAssist(turns: MeetingDisplayTurn[], enabled: boolean, call: LiveAssistCall = {}) {
  const [active, setActive] = useState<AssistCard | null>(null);
  const [earlier, setEarlier] = useState<AssistCard[]>([]);
  const [thinking, setThinking] = useState(false);
  const lastKeyRef = useRef("");
  /** How much of their current turn the last ask covered: the next ask is about what came after. */
  const askedRef = useRef<{ turnKey: string; length: number } | null>(null);
  const lastAskRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
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

  useEffect(() => {
    if (!context || key === lastKeyRef.current) return;
    // A settled sentence is asked about at once; words still settling only after a real pause.
    const wait = Math.max(askAfterMs({ settled: found!.settled }), lastAskRef.current + MIN_GAP_MS - Date.now());
    const timer = window.setTimeout(() => {
      lastKeyRef.current = key;
      askedRef.current = { turnKey: found!.turnKey, length: found!.length };
      lastAskRef.current = Date.now();
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setThinking(true);
      const askedAt = Date.now();
      note("ask", { latest: context.latestTurn, type: context.typeKey ?? null, mode: context.callMode ?? null });
      let draft: AssistCard | null = null;
      const onDraft = (card: AssistCard) => {
        if (controller.signal.aborted) return;
        if (draft) {
          // The same card growing while the answer streams: update it in place.
          if (card.id !== draft.id) return;
          draft = card;
          setActive((current) => (current?.id === card.id ? card : current));
          return;
        }
        if (coolingDown(card, lastShownRef.current, Date.now())) {
          note("draft-cooling", { label: card.label, ms: Date.now() - askedAt });
          return;
        }
        note("draft", { label: card.label, bridge: card.bridge, ms: Date.now() - askedAt });
        draft = card;
        present(card);
      };
      void Promise.all(ASSIST_SOURCES.map((source) => source.request(context, controller.signal, onDraft))).then((results) => {
        if (controller.signal.aborted) return;
        setThinking(false);
        const now = Date.now();
        const card = results.find((result) => result && (draft || !coolingDown(result, lastShownRef.current, now)));
        if (!card) {
          const cooling = results.find(Boolean);
          note(cooling ? "answer-cooling" : "silent", { label: cooling?.label ?? null, ms: now - askedAt });
          // The answer turned out not to be worth showing: withdraw the bridge quietly.
          if (draft) setActive((current) => (current?.id === draft!.id ? null : current));
          return;
        }
        // The answer takes the draft's place and keeps its clock, so timing counts from first sight.
        const shown = { ...card, id: draft?.id ?? card.id, at: draft?.at ?? now };
        lastShownRef.current[cooldownKey(shown)] = shown.at;
        note("answer", { label: shown.label, sayThis: shown.sayThis, thenAsk: shown.thenAsk, ms: now - askedAt });
        present(shown);
      });
    }, wait);
    return () => window.clearTimeout(timer);
    // The key captures every change in their words; context is derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (enabled) return;
    abortRef.current?.abort();
    setThinking(false);
    setActive(null);
  }, [enabled]);

  useEffect(() => () => abortRef.current?.abort(), []);

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
