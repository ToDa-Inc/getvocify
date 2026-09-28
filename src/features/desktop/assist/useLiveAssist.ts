import { useEffect, useRef, useState } from "react";
import {
  addCard,
  assistContext,
  cardVisible,
  cooldownKey,
  coolingDown,
  repActivityKey,
  CARD_MAX_MS,
  CARD_MIN_MS,
  type AssistCard,
} from "@/lib/live-assist";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";
import { ASSIST_SOURCES } from "./sources";

/** Wait for a pause in what they say before asking. */
const PAUSE_MS = 1500;
/** Never ask more often than this, so help never chases every word. */
const MIN_GAP_MS = 6000;

/**
 * Asks the assist sources after the other side pauses and applies the display
 * rules: one live card, 4–10s on screen, gone once the rep answers, and the same
 * kind of help waits a minute. Past cards stay readable under "Earlier".
 */
export function useLiveAssist(turns: MeetingDisplayTurn[], enabled: boolean) {
  const [active, setActive] = useState<AssistCard | null>(null);
  const [earlier, setEarlier] = useState<AssistCard[]>([]);
  const [thinking, setThinking] = useState(false);
  const [, setTick] = useState(0);
  const lastKeyRef = useRef("");
  const lastAskRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const lastShownRef = useRef<Record<string, number>>({});
  const repSpokeAtRef = useRef<number | null>(null);
  const repKeyRef = useRef("");

  const context = enabled ? assistContext(turns) : null;
  const key = context?.key ?? "";
  const repKey = repActivityKey(turns);

  if (repKey !== repKeyRef.current) {
    repKeyRef.current = repKey;
    if (repKey) repSpokeAtRef.current = Date.now();
  }

  const retire = (card: AssistCard) => {
    setActive((current) => (current?.id === card.id ? null : current));
    setEarlier((list) => addCard(list, card));
  };

  useEffect(() => {
    if (!context || key === lastKeyRef.current) return;
    const wait = Math.max(PAUSE_MS, lastAskRef.current + MIN_GAP_MS - Date.now());
    const timer = window.setTimeout(() => {
      lastKeyRef.current = key;
      lastAskRef.current = Date.now();
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setThinking(true);
      void Promise.all(ASSIST_SOURCES.map((source) => source.request(context, controller.signal))).then((results) => {
        if (controller.signal.aborted) return;
        setThinking(false);
        const now = Date.now();
        const card = results.find((result) => result && !coolingDown(result, lastShownRef.current, now));
        if (!card) return;
        const shown = { ...card, at: now };
        lastShownRef.current[cooldownKey(shown)] = now;
        setActive((current) => {
          if (current) setEarlier((list) => addCard(list, current));
          return shown;
        });
      });
    }, wait);
    return () => window.clearTimeout(timer);
    // The key captures every change in their words; context is derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Re-check visibility when the card could first step aside, and when it must leave.
  useEffect(() => {
    if (!active) return;
    const timers = [CARD_MIN_MS, CARD_MAX_MS].map((ms) =>
      window.setTimeout(() => setTick((n) => n + 1), Math.max(0, active.at + ms - Date.now()) + 20),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [active]);

  useEffect(() => {
    if (active && !cardVisible(active, Date.now(), repSpokeAtRef.current)) retire(active);
  });

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
    return localStorage.getItem(ENABLED_KEY) === "1";
  } catch {
    return false;
  }
}

/** Off until the rep turns it on (beta, not from their playbook); remembered per Mac. */
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
