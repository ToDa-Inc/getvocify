import { phraseTail, type MeetingDisplayTurn } from "./meeting-transcript.ts";
import type { ObjectionSuggestion } from "../features/copilot/types.ts";

/** What an assist source sees: the conversation so far and what they just said. */
export type AssistContext = {
  /** Their latest settled words, trimmed at a sentence or word. */
  latestTurn: string;
  /** "You: … / Them: …" lines, most recent last, capped for the prompt. */
  transcriptWindow: string;
};

/** One piece of live help, whatever produced it. */
export type AssistCard = {
  id: string;
  /** Which source produced it, e.g. "objection" or later "battle-card". */
  source: string;
  /** Short tag such as "Price" or a competitor name. */
  label: string;
  sayThis: string;
  thenAsk: string;
  why: string;
  avoid: string;
  at: number;
};

/**
 * Anything that turns the live conversation into help. Objection handling is the
 * first; battle cards plug in here once their endpoint exists. A source returns
 * null when it has nothing worth showing, and the panel stays quiet.
 */
export type AssistSource = {
  id: string;
  request: (context: AssistContext, signal: AbortSignal) => Promise<AssistCard | null>;
};

const MIN_WORDS = 4;
const LATEST_CHARS = 280;
const WINDOW_CHARS = 6000;

const OBJECTION_LABEL: Record<string, string> = {
  price: "Price",
  timing: "Timing",
  authority: "Decision maker",
  competitor: "Competitor",
  status_quo: "Status quo",
  trust: "Trust",
  other: "Objection",
};

/**
 * Ask only after the other side says something substantial; returns the key used
 * to avoid asking twice about the same words.
 */
export function assistContext(turns: MeetingDisplayTurn[]): (AssistContext & { key: string }) | null {
  const theirs = [...turns].reverse().find((turn) => turn.speaker === "prospect" && turn.text.trim());
  if (!theirs || theirs.text.trim().split(/\s+/).length < MIN_WORDS) return null;
  const latestTurn = phraseTail(theirs.text, LATEST_CHARS).replace(/^…/, "");
  const transcriptWindow = turns
    .filter((turn) => turn.text.trim())
    .map((turn) => (turn.label ? `${turn.label}: ${turn.text}` : turn.text))
    .join("\n")
    .slice(-WINDOW_CHARS);
  return { key: `${theirs.key}:${theirs.text.length}`, latestTurn, transcriptWindow };
}

/** Only a real objection with something to say becomes a card; no filler advice. */
export function objectionCard(suggestion: ObjectionSuggestion | null, at: number): AssistCard | null {
  if (!suggestion?.is_objection) return null;
  const sayThis = suggestion.say_this?.trim();
  if (!sayThis) return null;
  return {
    id: `objection-${at}`,
    source: "objection",
    label: OBJECTION_LABEL[suggestion.objection_type] ?? "Objection",
    sayThis,
    thenAsk: suggestion.next_question?.trim() ?? "",
    why: suggestion.why_it_works?.trim() ?? "",
    avoid: suggestion.dont_say?.trim() ?? "",
    at,
  };
}

/** Newest first, without repeating the same advice back to back. */
export function addCard(cards: AssistCard[], card: AssistCard, keep = 5): AssistCard[] {
  if (cards[0] && cards[0].sayThis === card.sayThis) return cards;
  return [card, ...cards].slice(0, keep);
}

/** F12 display rules: a card stays long enough to read, never lingers, never nags. */
export const CARD_MIN_MS = 4000;
export const CARD_MAX_MS = 10000;
export const CATEGORY_COOLDOWN_MS = 60000;

/** The same kind of help waits a minute before it can interrupt again. */
export function coolingDown(card: AssistCard, lastShown: Record<string, number>, now: number): boolean {
  const shownAt = lastShown[cooldownKey(card)];
  return shownAt !== undefined && now - shownAt < CATEGORY_COOLDOWN_MS;
}

export function cooldownKey(card: AssistCard): string {
  return `${card.source}:${card.label}`;
}

/**
 * A live card shows for at least 4s, at most 10s, and steps aside once the rep
 * starts answering (after those first 4s).
 */
export function cardVisible(card: AssistCard, now: number, repSpokeAt: number | null): boolean {
  const age = now - card.at;
  if (age >= CARD_MAX_MS) return false;
  if (age < CARD_MIN_MS) return true;
  return !(repSpokeAt !== null && repSpokeAt > card.at);
}

/** Changes whenever the rep says something new; used to notice they took the floor. */
export function repActivityKey(turns: MeetingDisplayTurn[]): string {
  const mine = [...turns].reverse().find((turn) => turn.speaker === "rep");
  return mine ? `${mine.key}:${mine.text.length}:${mine.pending.length}` : "";
}
