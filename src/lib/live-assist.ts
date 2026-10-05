import { phraseTail, type MeetingDisplayTurn } from "./meeting-transcript.ts";
import type { ObjectionSuggestion } from "../features/copilot/types.ts";

/** What an assist source sees: the conversation so far and what they just said. */
export type AssistContext = {
  /** Their latest settled words, trimmed at a sentence or word. */
  latestTurn: string;
  /** "You: … / Them: …" lines, most recent last, capped for the prompt. */
  transcriptWindow: string;
  /** The call's CRM contact, so help can use their earlier calls. */
  contactId?: string;
  /** How the call happens (a phone call or a meeting), from the platform that caught it. */
  callMode?: "softphone" | "meeting";
  /** The call's type: help uses that playbook. */
  typeKey?: string;
  /** The objection already on screen (from the turn check): the answer is written for it. */
  objectionType?: string;
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
  /** The one line to say; empty when no answer came (the filler line stays). */
  sayThis: string;
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

/**
 * The card while the answer is written: the objection's label and a filler line to say at once,
 * so the rep is never left in silence. The answer appears once, whole, below it: text is only
 * ever added, never replaced, so what the rep reads never changes under them.
 */
export function streamedDraft(streamed: string, latestTurn: string, at: number): AssistCard | null {
  const type = draftType(streamed);
  return type ? draftCard(type, latestTurn, at) : null;
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
    at,
  };
}

/**
 * Turn detection: has the prospect finished? Their audio going quiet says *when* to look, the
 * classifier says *whether* the thought is complete (a breath mid-sentence is not a turn end).
 * A real pause in their words is the backstop, and the only signal when no audio can be read.
 */
export const PAUSE_MS = 300;
/** After the classifier says "still going": this much more quiet and the turn is over. */
export const BACKSTOP_MS = 2000;

/** Their side's level (0–1, as the meter shows it) below which they are not speaking. */
export function prospectSilent(level: number): boolean {
  return level < 0.15;
}

/**
 * When to check their words, and whether that check is final (a "still going" verdict then counts
 * as done). paused: their audio has been quiet for PAUSE_MS; false while they speak; null when no
 * audio from their side has been read yet.
 */
export function turnCheck(input: { settled: boolean; paused: boolean | null }): { afterMs: number; final: boolean } {
  if (input.paused) return { afterMs: 0, final: false };
  if (input.paused === null && input.settled) return { afterMs: 300, final: true };
  return { afterMs: 2500, final: true };
}

/** What the turn check found; nulls when the classifier could not be reached. */
export type TurnReading = { finished: boolean | null; objection: string | null };

export type TurnStep = { do: "answer"; type: string } | { do: "wait" } | { do: "skip" } | { do: "ask" };

/** answer: show the card now and write its answer; ask: no classifier, let the answer model decide. */
export function nextStep(reading: TurnReading | null, final: boolean): TurnStep {
  if (!reading || reading.finished === null) return { do: "ask" };
  if (!reading.finished && !final) return { do: "wait" };
  const type = reading.objection;
  return type && type !== "none" && type in OBJECTION_LABEL ? { do: "answer", type } : { do: "skip" };
}

/**
 * The answer lands in the card already on screen and keeps its place, label, filler line and clock.
 * No answer (failed, silent or too slow) never takes the card away: the filler stays, the dots stop.
 */
export function answerCard(draft: AssistCard | null, answer: AssistCard | null): AssistCard | null {
  if (!draft) return answer;
  if (!answer) return { ...draft, stage: "ready" };
  return { ...answer, id: draft.id, at: draft.at, kind: draft.kind, label: draft.label, bridge: draft.bridge };
}

/** What a turn says on screen: its settled words, then the ones still settling. */
function spoken(turn: MeetingDisplayTurn): string {
  return [turn.text.trim(), turn.pending.trim()].filter(Boolean).join(" ");
}

export function assistContext(
  turns: MeetingDisplayTurn[],
  /** What the last ask already covered of their current turn: only the words since then are new. */
  asked?: { turnKey: string; length: number } | null,
): (AssistContext & { key: string; turnKey: string; length: number; settled: boolean }) | null {
  // Words still settling count: the transcription can take seconds to settle the end of a
  // sentence, and that end is usually the objection. A pause in what they say is enough.
  const theirs = [...turns].reverse().find((turn) => turn.speaker === "prospect" && spoken(turn));
  if (!theirs) return null;
  const said = spoken(theirs);
  // A prospect who says several things in a row stays one turn; help answers the newest of them,
  // never one it already answered.
  const covered = asked && asked.turnKey === theirs.key && asked.length < said.length ? asked.length : 0;
  const fresh = said.slice(covered).trim();
  if (fresh.split(/\s+/).length < MIN_WORDS) return null;
  const latestTurn = phraseTail(fresh, LATEST_CHARS).replace(/^…/, "");
  const transcriptWindow = turns
    .filter((turn) => spoken(turn))
    .map((turn) => (turn.label ? `${turn.label}: ${spoken(turn)}` : spoken(turn)))
    .join("\n")
    .slice(-WINDOW_CHARS);
  return {
    key: `${theirs.key}:${said.length}`,
    turnKey: theirs.key,
    length: said.length,
    settled: !theirs.pending.trim(),
    latestTurn,
    transcriptWindow,
  };
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
    at,
  };
}

/** Newest first, without repeating the same advice back to back. */
export function addCard(cards: AssistCard[], card: AssistCard, keep = 5): AssistCard[] {
  if (cards[0] && cards[0].sayThis === card.sayThis) return cards;
  return [card, ...cards].slice(0, keep);
}

/**
 * Display rules. A card stays until newer help replaces it (the rep may still be reading it out
 * loud); the replaced one moves to "Earlier". The same kind of help waits a minute before it can
 * interrupt again.
 */
export const CATEGORY_COOLDOWN_MS = 60000;

/** The same kind of help waits a minute before it can interrupt again. */
export function coolingDown(card: AssistCard, lastShown: Record<string, number>, now: number): boolean {
  const shownAt = lastShown[cooldownKey(card)];
  return shownAt !== undefined && now - shownAt < CATEGORY_COOLDOWN_MS;
}

export function cooldownKey(card: AssistCard): string {
  return `${card.source}:${card.label}`;
}

