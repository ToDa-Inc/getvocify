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
  /** Pushback to handle, or a product question to answer. */
  kind: "objection" | "question";
  /** "draft" while the answer is being written: only the label and a bridge line. */
  stage: "draft" | "ready";
  /** Something natural to say straight away while the real answer arrives. */
  bridge: string;
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
  request: (
    context: AssistContext,
    signal: AbortSignal,
    /** Called as soon as the source knows help is coming, before the full answer. */
    onDraft?: (draft: AssistCard) => void,
  ) => Promise<AssistCard | null>;
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
  question: "Question",
  other: "Objection",
};

/**
 * Said while the answer is being written. Plain and human on purpose: no "great
 * question", no "I understand your concern". Edit freely; keep them short.
 */
const BRIDGES: Record<string, { es: string; en: string }> = {
  price: { es: "Es normal mirarlo con lupa…", en: "Makes sense to look at the numbers…" },
  timing: { es: "Tiene sentido, el momento importa…", en: "Fair, timing matters…" },
  authority: { es: "Claro, que lo vea quien decide…", en: "Sure, the right people should see it…" },
  competitor: { es: "Bien que ya tengáis algo…", en: "Good that you already have something…" },
  status_quo: { es: "Si hoy os funciona, tiene sentido…", en: "If it works today, that makes sense…" },
  trust: { es: "Normal querer verlo antes…", en: "Fair to want proof first…" },
  question: { es: "Sí, te cuento…", en: "Sure, here's how it works…" },
  other: { es: "Te entiendo…", en: "I hear you…" },
};

/** Spanish unless the words say otherwise; the meeting's language drives the bridge. */
export function spokenLanguage(text: string): "es" | "en" {
  const lower = ` ${text.toLowerCase()} `;
  if (/[¿¡ñáéíóú]/.test(lower)) return "es";
  const es = (lower.match(/ (que|es|para|pero|con|los|las|una|nos|muy|está|tenemos) /g) ?? []).length;
  const en = (lower.match(/ (the|is|for|but|with|we|you|it's|that|this|have) /g) ?? []).length;
  return en > es ? "en" : "es";
}

export function bridgeLine(type: string, latestTurn: string): string {
  const lines = BRIDGES[type] ?? BRIDGES.other;
  return lines[spokenLanguage(latestTurn)];
}

/**
 * Reads the answer while it streams: once it says "objection, type X" we can show
 * the label and a bridge before the wording is done. The server still validates
 * the final answer; if it ends up silent the draft is withdrawn.
 */
export function draftType(partial: string): string | null {
  if (!/"is_objection"\s*:\s*true/.test(partial)) return null;
  const type = partial.match(/"objection_type"\s*:\s*"([a-z_]+)"/)?.[1];
  return type && type !== "none" && type in OBJECTION_LABEL ? type : null;
}

export function draftCard(type: string, latestTurn: string, at: number): AssistCard {
  return {
    id: `objection-${at}`,
    source: "objection",
    kind: type === "question" ? "question" : "objection",
    stage: "draft",
    bridge: bridgeLine(type, latestTurn),
    label: OBJECTION_LABEL[type] ?? "Objection",
    sayThis: "",
    thenAsk: "",
    why: "",
    avoid: "",
    at,
  };
}

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
export function objectionCard(suggestion: ObjectionSuggestion | null, at: number, latestTurn = ""): AssistCard | null {
  if (!suggestion?.is_objection) return null;
  const sayThis = suggestion.say_this?.trim();
  if (!sayThis) return null;
  const type = suggestion.objection_type;
  return {
    id: `objection-${at}`,
    source: "objection",
    kind: type === "question" ? "question" : "objection",
    stage: "ready",
    bridge: bridgeLine(type, latestTurn),
    label: OBJECTION_LABEL[type] ?? "Objection",
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

/**
 * Display rules. A card stays while it's being used: at least 8s, through the rep's
 * answer, gone 2.5s after they finish, never more than 25s. The same kind of help
 * waits a minute before interrupting again. (Longer than F12's 4–10s: in use, the
 * card vanished while the rep was reading it out loud.)
 */
export const CARD_MIN_MS = 8000;
export const CARD_MAX_MS = 25000;
export const REP_DONE_MS = 2500;
export const CATEGORY_COOLDOWN_MS = 60000;

/** The same kind of help waits a minute before it can interrupt again. */
export function coolingDown(card: AssistCard, lastShown: Record<string, number>, now: number): boolean {
  const shownAt = lastShown[cooldownKey(card)];
  return shownAt !== undefined && now - shownAt < CATEGORY_COOLDOWN_MS;
}

export function cooldownKey(card: AssistCard): string {
  return `${card.source}:${card.label}`;
}

/** `repLastAt`: when the rep last said anything (settled or in progress). */
export function cardVisible(card: AssistCard, now: number, repLastAt: number | null): boolean {
  const age = now - card.at;
  if (age >= CARD_MAX_MS) return false;
  if (age < CARD_MIN_MS) return true;
  const answered = repLastAt !== null && repLastAt > card.at;
  return !(answered && now - repLastAt >= REP_DONE_MS);
}

/** Changes whenever the rep says something new; used to notice they took the floor. */
export function repActivityKey(turns: MeetingDisplayTurn[]): string {
  const mine = [...turns].reverse().find((turn) => turn.speaker === "rep");
  return mine ? `${mine.key}:${mine.text.length}:${mine.pending.length}` : "";
}
