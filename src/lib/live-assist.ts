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
  /** The playbook's own objection the turn check matched (objectionType "custom"): its answer is followed. */
  entryId?: string;
  /** The filler line the rep is already saying: the answer is the next sentence after it. */
  filler?: string;
  /** The lines help already showed in this call, oldest first: the new answer must not repeat them. */
  previousAnswers?: string[];
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
/** The opening of the call (discovery: what they told us first) and its latest stretch, 15000 chars at most. */
const WINDOW_HEAD_CHARS = 3000;
const WINDOW_TAIL_CHARS = 12000;
const WINDOW_GAP = "[…]";

/**
 * The conversation for the prompt. A long call keeps its opening and its latest minutes, cut on
 * whole lines with a gap marker between: an objection at minute 20 can still be tied to what they
 * said at minute 2. The server accepts 20000 characters.
 */
export function windowOf(lines: string[]): string {
  if (lines.join("\n").length <= WINDOW_HEAD_CHARS + WINDOW_TAIL_CHARS) return lines.join("\n");
  let head = 0;
  let headChars = 0;
  while (head < lines.length && headChars + lines[head].length + 1 <= WINDOW_HEAD_CHARS) headChars += lines[head++].length + 1;
  let tail = lines.length;
  let tailChars = 0;
  while (tail > head && tailChars + lines[tail - 1].length + 1 <= WINDOW_TAIL_CHARS) tailChars += lines[--tail].length + 1;
  // One enormous line must not leave the window empty: it is cut, newest words kept.
  const newest = tail === lines.length ? [lines[tail - 1].slice(-WINDOW_TAIL_CHARS)] : lines.slice(tail);
  return [...lines.slice(0, head), WINDOW_GAP, ...newest].join("\n");
}

const OBJECTION_LABEL: Record<string, string> = {
  price: "Price",
  timing: "Timing",
  authority: "Decision maker",
  competitor: "Competitor",
  status_quo: "Status quo",
  trust: "Trust",
  question: "Question",
  other: "Objection",
  // One of the playbook's own objections: the card carries the entry's name.
  custom: "Objection",
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
  // Promises nothing: the answer may be "I'll confirm it".
  question: { es: "Mira…", en: "Right, so…" },
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

export function draftCard(type: string, latestTurn: string, at: number, label?: string): AssistCard {
  return {
    id: `objection-${at}`,
    source: "objection",
    kind: type === "question" ? "question" : "objection",
    stage: "draft",
    bridge: bridgeLine(type, latestTurn),
    label: label || (OBJECTION_LABEL[type] ?? "Objection"),
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

/**
 * After a card appears the rep is reading it, and saying it. No new check starts for this long, so the next
 * card never replaces one that is still being read. The prospect's words are not marked as handled meanwhile:
 * when the time is up, one check reads what they have said by then, so a fresh objection still gets a card.
 */
export const CARD_COOLDOWN_MS = 6_000;
/** A check that waited for the cooldown is skipped when the rep has said this many words since the prospect spoke. */
export const REP_ANSWERED_WORDS = 8;

/** How much longer to wait before a new check may start; 0 when no card is up or the time has passed. */
export function cooldownLeft(shownAt: number | null, now: number, cooldownMs = CARD_COOLDOWN_MS): number {
  return shownAt === null ? 0 : Math.max(0, shownAt + cooldownMs - now);
}

/**
 * Whether the rep has already answered the prospect's turn: they have said enough words since it. Then a card
 * written for it now would answer something already dealt with.
 */
export function repReplied(turns: MeetingDisplayTurn[], turnKey: string, minWords = REP_ANSWERED_WORDS): boolean {
  const at = turns.findIndex((turn) => turn.key === turnKey);
  if (at < 0) return false;
  const words = turns
    .slice(at + 1)
    .filter((turn) => turn.speaker === "rep")
    .reduce((total, turn) => total + (spoken(turn) ? spoken(turn).split(/\s+/).length : 0), 0);
  return words >= minWords;
}

/**
 * When the next check may start, decided when it is scheduled: it waits out the cooldown (never dropped: their
 * words stay unhandled). `deferred` says it had to wait.
 */
export function checkTiming(input: { afterMs: number; shownAt: number | null; now: number }): { waitMs: number; deferred: boolean } {
  const cooldown = cooldownLeft(input.shownAt, input.now);
  return { waitMs: Math.max(input.afterMs, cooldown), deferred: cooldown > input.afterMs };
}

/** Decided when the waiting check fires: skipped only if it waited and the rep has answered them meanwhile. */
export function skipAnswered(deferred: boolean, turns: MeetingDisplayTurn[], turnKey: string): boolean {
  return deferred && repReplied(turns, turnKey);
}

/** Their side's level (0–1, as the meter shows it) below which they are not speaking, on a clean line. */
export const SILENT_LEVEL = 0.15;
/** Whatever the line, quiet is never above this: speech is never called quiet. */
export const SILENT_LEVEL_MAX = 0.4;
/** Quiet is this far above the line's own noise, and under this share of how loud they have recently been. */
const SILENT_MARGIN = 0.08;
const SILENT_SHARE_OF_PEAK = 0.35;
/** How far back the noise floor and the speech peak look, and how much audio they need before they are trusted. */
export const FLOOR_WINDOW_MS = 10_000;
const FLOOR_MIN_SPAN_MS = 3_000;

/** What the last seconds of their audio say about the line: its noise (lowest level) and its voice (highest). */
export type LineLevels = { floor: number; peak: number };

/**
 * The line's noise floor and speech peak: the lowest and highest level read in the last FLOOR_WINDOW_MS, once at
 * least FLOOR_MIN_SPAN_MS of readings exist (null before). Speech never lasts ten seconds without a dip, so the
 * lowest reading is the noise.
 */
export function lineLevels(readings: { t: number; level: number }[], now: number): LineLevels | null {
  const recent = readings.filter((reading) => now - reading.t <= FLOOR_WINDOW_MS);
  if (!recent.length || now - recent[0].t < FLOOR_MIN_SPAN_MS) return null;
  const levels = recent.map((reading) => reading.level);
  return { floor: Math.min(...levels), peak: Math.max(...levels) };
}

/**
 * The level under which they are not speaking. It follows the line, not a fixed number: above the line's own noise
 * (a real microphone or a phone line is never silent) and under a share of how loud this speaker has been (a quiet
 * speaker and a loud one both drop well below their own voice when they stop). Before any audio is known, the
 * clean-line level.
 */
export function silentLevel(line: LineLevels | null): number {
  if (line === null) return SILENT_LEVEL;
  return Math.min(SILENT_LEVEL_MAX, Math.max(SILENT_LEVEL, line.floor + SILENT_MARGIN, line.peak * SILENT_SHARE_OF_PEAK));
}

export function prospectSilent(level: number, line: LineLevels | null = null): boolean {
  return level < silentLevel(line);
}

/** How long a check waits when their audio gives no pause: their words have settled by then (about 0.1-0.5 s after they stop). */
export const FALLBACK_MS = 1000;

/**
 * When to check their words, and whether that check is final (a "still going" verdict then counts
 * as done). paused: their audio has been quiet for PAUSE_MS; false while they speak; null when no
 * audio from their side has been read yet.
 */
export function turnCheck(input: { settled: boolean; paused: boolean | null }): { afterMs: number; final: boolean } {
  if (input.paused) return { afterMs: 0, final: false };
  if (input.paused === null && input.settled) return { afterMs: 300, final: true };
  return { afterMs: FALLBACK_MS, final: true };
}

/** Which rule started a check: their audio paused, the words had settled, the slow fallback, or the backstop. */
export type CheckPath = "pause" | "settled" | "timeout" | "backstop";

/** The path turnCheck takes for these inputs (the same three cases), to say which one fired. */
export function checkPath(paused: boolean | null, settled: boolean): Exclude<CheckPath, "backstop"> {
  if (paused) return "pause";
  return paused === null && settled ? "settled" : "timeout";
}

/**
 * What the client saw when a check started, sent with it so the event log can say where the time went:
 * how long their audio had been quiet, how long since the transcript last changed, and whether the words
 * were still changing after their audio went quiet (tail_ms > 0: the transcript lags the voice).
 */
export type CheckStamps = {
  path: CheckPath;
  quiet_ms: number | null;
  words_age_ms: number;
  tail_ms: number | null;
  wait_ms: number;
  deferred: boolean;
  final: boolean;
  /** Their audio level and the noise floor at that moment, in percent (0-100); null before any was read. */
  level_pct: number | null;
  floor_pct: number | null;
};

export function checkStamps(input: {
  path: CheckPath;
  now: number;
  quietSince: number | null;
  changedAt: number;
  waitMs: number;
  deferred: boolean;
  final: boolean;
  level?: number | null;
  floor?: number | null;
}): CheckStamps {
  return {
    path: input.path,
    quiet_ms: input.quietSince === null ? null : Math.max(0, input.now - input.quietSince),
    words_age_ms: Math.max(0, input.now - input.changedAt),
    tail_ms: input.quietSince === null ? null : input.changedAt - input.quietSince,
    wait_ms: input.waitMs,
    deferred: input.deferred,
    final: input.final,
    level_pct: pct(input.level),
    floor_pct: pct(input.floor),
  };
}

function pct(value: number | null | undefined): number | null {
  return typeof value === "number" ? Math.round(value * 100) : null;
}

/** What the turn check found; nulls when the classifier could not be reached. */
export type TurnReading = {
  finished: boolean | null;
  objection: string | null;
  /** With objection "custom": which of the playbook's own objections it is, and its name. */
  entry_id?: string;
  label?: string;
};

export type TurnStep =
  | { do: "answer"; type: string; entryId?: string; label?: string }
  | { do: "wait" }
  | { do: "skip" }
  | { do: "ask" };

/** answer: show the card now and write its answer; ask: no classifier, let the answer model decide. */
export function nextStep(reading: TurnReading | null, final: boolean): TurnStep {
  if (!reading || reading.finished === null) return { do: "ask" };
  if (!reading.finished && !final) return { do: "wait" };
  const type = reading.objection;
  if (type === "custom" && reading.entry_id) {
    return { do: "answer", type, entryId: reading.entry_id, ...(reading.label && { label: reading.label }) };
  }
  return type && type !== "none" && type !== "custom" && type in OBJECTION_LABEL ? { do: "answer", type } : { do: "skip" };
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
  const transcriptWindow = windowOf(
    turns.filter((turn) => spoken(turn)).map((turn) => (turn.label ? `${turn.label}: ${spoken(turn)}` : spoken(turn))),
  );
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

const PREVIOUS_ANSWERS = 6;

/** The lines already shown in this call, oldest first and each once: the next answer must differ. */
export function previousAnswers(shown: AssistCard[]): string[] {
  const lines = shown.map((card) => card.sayThis.trim()).filter(Boolean);
  return [...new Set(lines)].slice(-PREVIOUS_ANSWERS);
}

/**
 * Display rules. A card stays until newer help replaces it (the rep may still be reading it out
 * loud); nothing older is kept on screen. Every new objection or question gets its answer, even of
 * the same type as the one on screen: it replaces that card, once its cooldown is over.
 */
