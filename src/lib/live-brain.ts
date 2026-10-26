// The dashboard side of the live call assistant's brain (spec 2026-10-16-live-call-assistant-design.md): what a reading
// sends, when a reading happens, how a stream of tokens becomes a draft, and what the views draw from the state. Pure: the
// hook (features/desktop/assist/useLiveBrain.ts) does the I/O. The state and its merging are shared/live-call/state.js.
//
// No `@/` imports: this file runs under node --test.
import type { MeetingDisplayTurn } from "./meeting-transcript.ts";
import { islandBrief } from "./desktop-call.ts";
import { emptyLiveState, pointsIn, progressIn } from "../../shared/live-call/state.js";

/**
 * Why a reading happens: the checkpoint, or the rep asking (the wire's `reason`). "rewrite": another version of a point on
 * screen; "ask_step": a question for one pending step or data item (build contract 2026-10-20, §2).
 */
export type LiveReason = "turn_end" | "long_turn" | "rep_turn" | "responder" | "preguntar" | "resumen" | "rewrite" | "ask_step";
export const ASKED_REASONS: readonly LiveReason[] = ["responder", "preguntar", "resumen", "rewrite", "ask_step"];

/** What a rewrite or a step question is about (the wire's `target`). */
export type ReadingTarget =
  | { point_id: string; version: number }
  | { kind: "step" | "data"; id: string };

/** The turns the backend takes (live_models.MAX_TURNS); a longer call keeps its opening and its latest stretch. */
export const MAX_TURNS = 400;
const HEAD_TURNS = 40;
const TURN_CHARS = 4000;
/** Responder reads about the last minute (the spec's RESPOND_WINDOW). */
export const RESPOND_WINDOW_S = 60;
/** During a long prospect turn, a reading at a breath once this long has passed since the last one. */
export const LONG_TURN_MS = 15_000;
/** The rep's words since the last reading that make a reading worth it (their lines may settle a point or tick a step). */
export const REP_WORDS = 8;
/** The rep has to be quiet this long before their turn is read, and readings after their turns are this far apart. */
export const REP_QUIET_MS = 1500;
export const REP_GAP_MS = 6000;
/** Failed readings in a row before the views say "Sin conexión". */
export const OFFLINE_AFTER = 2;
/** Open points that show in full; older open ones wait as one line. */
export const OPEN_IN_FULL = 2;

export type WireTurn = { id: string; who: "them" | "you"; name?: string; text: string; t: number };

/** What a turn says on screen: its settled words, then the ones still settling. */
export function spoken(turn: Pick<MeetingDisplayTurn, "text" | "pending">): string {
  return [turn.text.trim(), turn.pending.trim()].filter(Boolean).join(" ");
}

/** The call as the backend wants it. A turn with no known side is left out: the brain never guesses who spoke. */
export function toWireTurns(turns: MeetingDisplayTurn[]): WireTurn[] {
  const wire = turns.flatMap((turn): WireTurn[] => {
    const text = spoken(turn);
    if (!text || !turn.speaker) return [];
    return [
      {
        id: turn.key,
        who: turn.speaker === "prospect" ? "them" : "you",
        ...(turn.name ? { name: turn.name.slice(0, 80) } : {}),
        text: text.length > TURN_CHARS ? text.slice(-TURN_CHARS) : text,
        t: Math.max(0, turn.start ?? 0),
      },
    ];
  });
  return wire.length <= MAX_TURNS ? wire : [...wire.slice(0, HEAD_TURNS), ...wire.slice(wire.length - (MAX_TURNS - HEAD_TURNS))];
}

/** Words the rep has said in the whole call: a reading after their turns happens once enough new ones are there. */
export function repWords(turns: MeetingDisplayTurn[]): number {
  return turns
    .filter((turn) => turn.speaker === "rep")
    .reduce((total, turn) => total + (spoken(turn) ? spoken(turn).split(/\s+/).length : 0), 0);
}

/** A reading after the rep spoke: enough new words since the last one, and not sooner than REP_GAP_MS after it. */
export function repReadingDue(input: { words: number; readWords: number; lastReadAt: number | null; now: number }): boolean {
  if (input.words - input.readWords < REP_WORDS) return false;
  return input.lastReadAt === null || input.now - input.lastReadAt >= REP_GAP_MS;
}

/** What the last reading covered of their newest turn (the turn's key and how much of its text). */
export type ReadMark = { turnKey: string; length: number } | null;

/**
 * A long prospect turn gets a reading at a breath, once LONG_TURN_MS has passed since the last one. `finished` false means
 * the turn check saw a breath, not an end.
 */
export function longTurnDue(input: { lastReadAt: number | null; now: number }): boolean {
  return input.lastReadAt === null || input.now - input.lastReadAt >= LONG_TURN_MS;
}

/**
 * The turn where a reading's window starts; turns before it are context. An automatic reading starts a little before the
 * previous one ended (one turn of overlap); Responder starts about a minute before the tap.
 */
export function focusFor(reason: LiveReason, turns: WireTurn[], mark: ReadMark): string | null {
  if (!turns.length) return null;
  if (reason === "responder") {
    const last = turns[turns.length - 1].t;
    if (last <= RESPOND_WINDOW_S) return turns[0].id;
    if (turns.every((turn) => turn.t === 0)) return turns[Math.max(0, turns.length - 8)].id;
    return (turns.find((turn) => turn.t >= last - RESPOND_WINDOW_S) ?? turns[0]).id;
  }
  if (reason === "resumen" || reason === "preguntar" || reason === "rewrite" || reason === "ask_step") return null;
  if (!mark) return null;
  const at = turns.findIndex((turn) => turn.id === mark.turnKey);
  return at < 0 ? null : turns[Math.max(0, at - 1)].id;
}

export type ReadingCall = {
  callId: string;
  callMode: "softphone" | "meeting";
  contactId?: string | null;
  typeKey?: string | null;
  typeLabel?: string | null;
};

type StateLike = ReturnType<typeof import("../../shared/live-call/state.js").emptyLiveState>;

/** One reading as live_models.LiveReading wants it. */
export function buildReading(input: {
  call: ReadingCall;
  turns: WireTurn[];
  state: StateLike;
  reason: LiveReason;
  mark?: ReadMark;
  /** Which producer's cursor goes with it: a reading whose words were all read already is skipped (asked ones never are). */
  producer: "points" | "progress" | "recap";
  typeChanged?: boolean;
  target?: ReadingTarget | null;
  /** The "Qué decir" view is on (flag LIVE_SAY_VIEW_ENABLED): the brain may suggest questions to go deeper. */
  sayView?: boolean;
  /** Responder about one tapped bubble: the window starts (and the turns end) at that turn. */
  focusTurn?: string | null;
}): Record<string, unknown> {
  const { call, state, reason } = input;
  const points = pointsIn(state)
    .slice(-24)
    .map((point) => ({ ...point, say: point.say ? point.say.slice(0, 400) : null, versions: point.versions.slice(0, 8).map((v: string) => v.slice(0, 400)) }));
  const focus = input.focusTurn ?? focusFor(reason, input.turns, input.mark ?? null);
  const cursor = state.cursors[input.producer === "points" ? "points" : "progress"];
  return {
    call_id: call.callId,
    call_mode: call.callMode,
    language: "auto",
    ...(call.typeKey ? { sales_motion_key: call.typeKey } : {}),
    ...(call.typeLabel ? { type_label: call.typeLabel } : {}),
    ...(call.contactId ? { contact_id: call.contactId } : {}),
    reason,
    turns: input.turns,
    ...(focus ? { focus_from: focus } : {}),
    state_version: state.version,
    ...(cursor && !ASKED_REASONS.includes(reason) ? { cursor } : {}),
    points,
    progress: progressIn(state),
    ...(input.typeChanged ? { type_changed: true } : {}),
    ...(input.producer === "recap" && input.turns.length ? { up_to: input.turns[input.turns.length - 1].id } : {}),
    ...(input.target ? { target: input.target } : {}),
    say_view: Boolean(input.sayView),
  };
}

/** A card of the strategic producer as it goes back to it: every card shown in this call, oldest first, with whether it is
 * still on screen (the rep has not closed it and no newer card replaced it). The producer's points carry `visible_t`. */
export type CardIn = { id: string; say: string; visible_t: number; open: boolean };

export function cardsIn(state: StateLike): CardIn[] {
  return state.points
    .flatMap((point: { id: string; outcome: string; versions?: string[]; answer?: string | null; visible_t?: unknown }): CardIn[] =>
      typeof point.visible_t === "number"
        ? [{ id: point.id, say: (point.versions?.[0] ?? point.answer ?? "").slice(0, 400), visible_t: point.visible_t, open: point.outcome === "open" }]
        : [],
    )
    .slice(-60);
}

/** One reading of the strategic card (pilot, flag LIVE_CARD_ENABLED, live_models.CardReading): an automatic checkpoint with the
 * cards already shown, what the turn check saw in their latest turn and the previous reading's `read_t`. */
export function buildCardReading(input: {
  call: ReadingCall;
  turns: WireTurn[];
  state: StateLike;
  reason: LiveReason;
  mark?: ReadMark;
  sayView?: boolean;
  objection?: string | null;
  lastReadT?: number | null;
}): Record<string, unknown> {
  return {
    ...buildReading({ ...input, producer: "points" }),
    cards: cardsIn(input.state),
    ...(input.objection ? { objection: input.objection.slice(0, 200) } : {}),
    ...(typeof input.lastReadT === "number" ? { last_read_t: input.lastReadT } : {}),
  };
}

/** What the turn check saw, as the card producer wants it: the playbook entry for one of its own objections, else the type. */
export function turnObjection(turn: { objection: string | null; entry_id?: string } | null): string | null {
  if (!turn?.objection) return null;
  return turn.objection === "custom" && turn.entry_id ? turn.entry_id : turn.objection;
}

/** The call up to and including one turn (Responder about a tapped bubble reads that sentence); null when it is not there. */
export function turnsUpTo(turns: WireTurn[], turnId: string): WireTurn[] | null {
  const at = turns.findIndex((turn) => turn.id === turnId);
  return at < 0 ? null : turns.slice(0, at + 1);
}

// ---------- the points stream ----------

/** A point being written, or one the turn check just spotted: `kind` is what it is ("price", "question"...) as soon as it is known. */
export type StreamedPoint = { title: string | null; say: string | null; grounded: boolean | null; kind?: string | null; tag?: string | null };

/** The text of a JSON string value being written (the closing quote may not be there yet). */
function partialString(chunk: string, key: string): string | null {
  const at = chunk.search(new RegExp(`"${key}"\\s*:\\s*"`));
  if (at < 0) return null;
  const start = chunk.indexOf('"', chunk.indexOf(":", at)) + 1;
  let raw = "";
  for (let i = start; i < chunk.length; i += 1) {
    const char = chunk[i];
    if (char === "\\") {
      if (i + 1 >= chunk.length) break;
      raw += char + chunk[i + 1];
      i += 1;
      continue;
    }
    if (char === '"') break;
    raw += char;
  }
  // A \uXXXX cut in the middle is not yet a character.
  raw = raw.replace(/\\u[0-9a-fA-F]{0,3}$/, "");
  try {
    return JSON.parse(`"${raw}"`) as string;
  } catch {
    return raw.replace(/\\(.)/g, "$1");
  }
}

/**
 * The points the model is writing, read from the JSON text streamed so far (the model writes `{"points": [{…, "quote", …,
 * "say"}]}`). Only a draft: the result event is the point, and it may differ (the guards can drop a claim).
 */
export function streamedPoints(text: string): StreamedPoint[] {
  const body = text.split(/"closed"\s*:/)[0];
  const chunks = body.split(/\{\s*"ref"\s*:/).slice(1);
  return chunks.map((chunk) => {
    const grounded = /"grounded"\s*:\s*(true|false)/.exec(chunk);
    return {
      kind: partialString(chunk, "type")?.trim() || null,
      title: partialString(chunk, "quote")?.trim() || null,
      say: partialString(chunk, "say")?.trim() || null,
      grounded: grounded ? grounded[1] === "true" : null,
    };
  });
}

/**
 * What the turn check (~0.3 s) just spotted, as a card being written: what it is and their words, before the brain answers.
 * Null when it is nothing to answer ("none", or no verdict).
 */
export function spottedDraft(turn: { objection: string | null; entry_id?: string; label?: string } | null, latest: string): StreamedPoint | null {
  const kind = turn?.objection;
  if (!kind || kind === "none") return null;
  const sentences = latest.split(/(?<=[.?!…])\s+/).filter((sentence) => sentence.trim());
  const words = (sentences[sentences.length - 1] ?? latest).trim().split(/\s+/).filter(Boolean);
  const title = words.slice(-10).join(" ");
  return { kind: kind === "custom" ? turn.entry_id ?? "other" : kind, tag: turn.label ?? null, title: title || null, say: null, grounded: null };
}

// ---------- the playbook's words for the ids ----------

export type StepPart = { id: string; label: string };
export type PlaybookStep = {
  id: string;
  label: string;
  criterion: string;
  example: string | null;
  concept: string | null;
  live: boolean;
  /** Only for a step whose criterion lists parts: the parts, and how many of them make it done. */
  parts?: StepPart[];
  need?: number;
};
export type PlaybookDatum = { id: string; label: string; good: string | null; question: string | null };
export type PlaybookView = {
  key: string | null;
  name: string | null;
  has_playbook: boolean;
  steps: PlaybookStep[];
  data: PlaybookDatum[];
};

type EditorLike = {
  steps?: { step_id: string; label: string; criterion?: string; example?: string }[];
  qualification?: { criterion_id: string; label: string; good?: string }[];
} | null;
type AidsLike = {
  steps?: Record<string, { concept?: string | null; live?: boolean }>;
  data?: Record<string, { question?: string | null }>;
} | null;
type PartListsLike = Record<string, { parts: StepPart[]; need: number }> | null | undefined;

/**
 * The playbook of the call's type as the views draw it: the editor's steps and criteria, with the producer's aids and the
 * parts it listed for steps whose criterion lists them.
 */
export function playbookView(input: {
  key: string | null;
  name: string | null;
  hasPlaybook: boolean;
  editor: EditorLike;
  aids: AidsLike;
  partLists?: PartListsLike;
}): PlaybookView {
  const { editor, aids } = input;
  const partsOf = (id: string) => {
    const list = input.partLists?.[id];
    return list?.parts.length ? { parts: list.parts.map(({ id: part, label }) => ({ id: part, label })), need: list.need } : {};
  };
  return {
    key: input.key,
    name: input.name,
    has_playbook: input.hasPlaybook,
    steps: (editor?.steps ?? []).map((step) => ({
      id: step.step_id,
      label: step.label,
      criterion: step.criterion ?? "",
      example: step.example?.trim() || null,
      concept: aids?.steps?.[step.step_id]?.concept ?? null,
      live: aids?.steps?.[step.step_id]?.live !== false,
      ...partsOf(step.step_id),
    })),
    data: (editor?.qualification ?? []).map((item) => ({
      id: item.criterion_id,
      label: item.label,
      good: item.good?.trim() || null,
      question: aids?.data?.[item.criterion_id]?.question ?? null,
    })),
  };
}

// ---------- what the views draw ----------

type Progress = StateLike["progress"];
type Point = StateLike["points"][number];

export type ItemKind = "step" | "data" | "goal";
export type FaltaItem = {
  kind: ItemKind;
  id: string;
  label: string;
  /** What to ask or say for it; null when there is nothing (then its name is not a button). */
  ask: string | null;
  /** The step's few words and criterion, or the data's good answer: the name's tooltip. */
  tip: string | null;
  /** The brain's pick. */
  picked: boolean;
};
export type HechoItem = { kind: ItemKind; id: string; label: string; detail: string | null; by: "brain" | "rep"; reread: boolean };
export type ProgressView = {
  hasPlaybook: boolean;
  noSteps: boolean;
  name: string | null;
  total: number;
  done: number;
  now: { kind: ItemKind; id: string; label: string; say: string } | null;
  falta: FaltaItem[];
  hecho: HechoItem[];
  /** The brain's picks still missing that the rep has not ticked (at most 2): the Conversación tab's count. */
  picks: number;
};

/** "plantear_el_problema" → "Plantear el problema": the id as a name when the playbook's words are not there. */
export function humanize(id: string): string {
  const words = id.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : id;
}

/** Where the call stands against the playbook, in the order the spec draws it (Ahora, Falta, Hecho). */
export function progressView(progress: Progress, playbook: PlaybookView | null, goalLabel: string): ProgressView {
  const steps = (playbook?.steps ?? []).filter((step) => step.live);
  const data = playbook?.data ?? [];
  const stepOf = (id: string) => steps.find((step) => step.id === id);
  const datumOf = (id: string) => data.find((item) => item.id === id);
  const doneStep = (id: string) => Boolean(progress.steps[id]);
  const doneDatum = (id: string) => Boolean(progress.data[id]);
  const goalPending = (): boolean => !progress.goal;
  const goalKnown = Boolean(progress.goal) || progress.now?.kind === "goal" || progress.missing.includes("goal");

  const label = (kind: ItemKind, id: string): string =>
    kind === "step" ? stepOf(id)?.label ?? humanize(id) : kind === "data" ? datumOf(id)?.label ?? humanize(id) : goalLabel;
  const item = (kind: ItemKind, id: string): FaltaItem => {
    const step = kind === "step" ? stepOf(id) : undefined;
    const datum = kind === "data" ? datumOf(id) : undefined;
    const ask = kind === "step" ? step?.example ?? null : kind === "data" ? datum?.question ?? null : null;
    const tip =
      kind === "step"
        ? [step?.concept, step?.criterion].filter(Boolean).join(" · ") || null
        : kind === "data"
          ? datum?.good ?? null
          : null;
    return { kind, id, label: label(kind, id), ask, tip, picked: progress.missing.includes(id) };
  };
  const pending = (kind: ItemKind, id: string): boolean =>
    kind === "step" ? Boolean(stepOf(id)) && !doneStep(id) : kind === "data" ? Boolean(datumOf(id)) && !doneDatum(id) : goalKnown && goalPending();

  const falta: FaltaItem[] = [];
  const add = (kind: ItemKind, id: string) => {
    if (pending(kind, id) && !falta.some((entry) => entry.id === id)) falta.push(item(kind, id));
  };
  for (const id of progress.missing) add(id === "goal" ? "goal" : stepOf(id) ? "step" : "data", id);
  for (const step of steps) add("step", step.id);
  for (const datum of data) add("data", datum.id);
  add("goal", "goal");

  const hecho: HechoItem[] = [];
  for (const step of steps) {
    const found = progress.steps[step.id];
    if (found) hecho.push({ kind: "step", id: step.id, label: step.label, detail: found.by === "rep" ? null : found.quote ?? null, by: found.by, reread: false });
  }
  for (const datum of data) {
    const found = progress.data[datum.id];
    if (found) {
      hecho.push({ kind: "data", id: datum.id, label: datum.label, detail: found.by === "rep" ? null : found.value ?? found.quote ?? null, by: found.by, reread: Boolean(found.reread) });
    }
  }
  if (progress.goal) hecho.push({ kind: "goal", id: "goal", label: goalLabel, detail: progress.goal.by === "rep" ? null : progress.goal.value ?? progress.goal.quote ?? null, by: progress.goal.by, reread: false });
  // Ids the brain ticked that the playbook words do not cover (the editor could not be read): still shown, by id.
  for (const id of Object.keys(progress.steps)) if (!stepOf(id)) hecho.push({ kind: "step", id, label: humanize(id), detail: progress.steps[id].by === "rep" ? null : progress.steps[id].quote, by: progress.steps[id].by, reread: false });
  for (const id of Object.keys(progress.data)) if (!datumOf(id)) hecho.push({ kind: "data", id, label: humanize(id), detail: progress.data[id].by === "rep" ? null : progress.data[id].value ?? null, by: progress.data[id].by, reread: Boolean(progress.data[id].reread) });

  let now: ProgressView["now"] = null;
  const forNow = progress.now && pending(progress.now.kind, progress.now.id) ? item(progress.now.kind, progress.now.id) : null;
  if (forNow) {
    const say = progress.now?.say ?? forNow.ask;
    if (say) now = { kind: forNow.kind, id: forNow.id, label: forNow.label, say };
  }
  if (!now) {
    const first = falta.find((entry) => entry.ask);
    if (first) now = { kind: first.kind, id: first.id, label: first.label, say: first.ask as string };
  }

  // Ahora is the same item as the head of Falta: it is drawn once, in Ahora.
  const rest = now ? falta.filter((entry) => entry.id !== now!.id) : falta;
  const total = steps.length + data.length + (goalKnown ? 1 : 0);
  const done = steps.filter((step) => doneStep(step.id)).length + data.filter((datum) => doneDatum(datum.id)).length + (progress.goal ? 1 : 0);
  const picks = progress.missing.filter((id) => pending(id === "goal" ? "goal" : stepOf(id) ? "step" : "data", id)).slice(0, 2).length;
  return {
    hasPlaybook: Boolean(progress.has_playbook || playbook?.has_playbook),
    noSteps: steps.length === 0,
    name: progress.playbook?.name ?? playbook?.name ?? null,
    total,
    done,
    now,
    falta: rest,
    hecho,
    picks,
  };
}

export type PointsView = {
  /** Open points, oldest first. The newest OPEN_IN_FULL show in full, the rest as one line. */
  open: Point[];
  full: Set<string>;
  /** Open points that wait for an answer: a question to go deeper ("deepen") is available, never a task, so not counted. */
  waiting: Point[];
  /** Everything else, oldest first: the "Antes" list. */
  before: Point[];
  unanswered: number;
};

export function pointsView(points: Point[], expanded: ReadonlySet<string> = new Set()): PointsView {
  const open = points.filter((point) => point.outcome === "open");
  const newest = open.slice(Math.max(0, open.length - OPEN_IN_FULL)).map((point) => point.id);
  return {
    open,
    full: new Set([...newest, ...open.filter((point) => expanded.has(point.id)).map((point) => point.id)]),
    waiting: open.filter((point) => point.kind !== "deepen"),
    before: points.filter((point) => point.outcome !== "open"),
    unanswered: points.filter((point) => point.outcome === "unanswered").length,
  };
}

/** What a point shows as the words to say: the answer, else the honest line when the fact is not written. */
export function pointSays(point: Pick<Point, "answer" | "fallback">): string {
  return (point.answer ?? point.fallback ?? "").trim();
}

// ---------- what travels to the island ----------

export type LiveDraft = StreamedPoint;
/** Responder with nothing to answer: the missing item that matters most for the call's goal and its question, or with nothing
 * pending ("said") a question that takes up the last thing they said (`id` its turn, `label` their words). */
export type NextAsk = { kind: "step" | "data" | "said"; id: string; label: string; question: string };
export type LiveBrainAsks = {
  responder: null | { seq: number; status: "reading" | "found" | "nothing"; point_id: string | null; next: NextAsk | null };
  recap: null | { seq: number; status: "reading" | "ready"; up_to_t: number | null; lines: string[]; unknown: string[] };
  /** A question for one pending item (Pasos tap). */
  step: null | { seq: number; kind: "step" | "data"; id: string; status: "reading" | "ready"; question: string | null };
  /** Another version of a point on screen; "none": the brain had no other honest angle. */
  rewrite: null | { seq: number; point_id: string; status: "reading" | "ready" | "none" };
};

/** The responder result's `next`, when it is whole. */
export function nextAsk(raw: unknown): NextAsk | null {
  if (!raw || typeof raw !== "object") return null;
  const next = raw as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" && value.trim() ? value.trim() : null);
  const kind = next.kind === "step" || next.kind === "data" || next.kind === "said" ? next.kind : null;
  const id = text(next.id);
  const label = text(next.label);
  const question = text(next.question);
  return kind && id && label && question ? { kind, id, label, question } : null;
}

// ---------- the contact: who they are before this call ----------

/** Who the contact is before this call, for the island's contact button (null: no button). */
export type LiveContact = { name: string; company: string | null; first: boolean; lines: string[] };

const CONTACT_KINDS = ["emails", "notes", "calls", "meetings", "tasks"];

type ActivityLike = Parameters<typeof islandBrief>[0] & {
  interactions?: unknown[] | null;
  sources?: { hubspot?: Record<string, string> | null; vocify?: string | null } | null;
};

/**
 * The contact's brief from GET /contacts/{id}/recent-activity, only with what it says: its summary's lines (the contact's,
 * then those about others at its company) and the company's name. `first` only when every source was read and there is no
 * earlier interaction with them; while the activity loads, or when it could not be read, there are no lines and `first`
 * is false. No name: no contact.
 */
export function contactBrief(name: string | null | undefined, activity: ActivityLike | null | undefined): LiveContact | null {
  const shown = name?.trim();
  if (!shown) return null;
  const brief = islandBrief(activity);
  const lines = brief?.state === "ready" ? [...brief.lines, ...(brief.company?.lines ?? [])].map((line) => line.text) : [];
  // "First contact" is said only when the contact's own activity was read whole: each HubSpot kind and Vocify's calls.
  const sources = activity?.sources;
  const allRead = sources?.vocify === "read" && CONTACT_KINDS.every((kind) => sources?.hubspot?.[kind] === "read");
  const first = Boolean(activity) && allRead && !(activity?.interactions ?? []).length && !lines.length;
  return { name: shown, company: activity?.company?.name?.trim() || null, first, lines };
}

/** The whole payload of shell.setState({ liveBrain }) (build contract 2026-10-20-live-say-view-build-contract.md, §4). */
export function liveBrainPayload(input: {
  on: boolean;
  callId: string;
  state: StateLike;
  playbook: PlaybookView | null;
  reading: { points: boolean; progress: boolean; recap: boolean };
  offlineSince: number | null;
  drafts: LiveDraft[];
  asks: LiveBrainAsks;
  typeChanged: boolean;
  /** "say": the island draws the "Qué decir" view (flag LIVE_SAY_VIEW_ENABLED); "tabs": today's tabs. */
  view: "say" | "tabs";
  contact: LiveContact | null;
}) {
  return {
    view: input.view,
    on: input.on,
    call_id: input.callId,
    state: input.state,
    playbook: input.playbook,
    reading: input.reading,
    offline_since: input.offlineSince,
    drafts: input.drafts,
    asks: input.asks,
    type_changed: input.typeChanged,
    contact: input.contact,
  };
}

/**
 * The call's type changed to another one: the new playbook comes in as a whole (its steps start unticked, read again against
 * the call so far), the rep's marks belonged to the old playbook's ids, and the open points stay.
 */
export function resetForType(state: StateLike): StateLike {
  const fresh = emptyLiveState(state.call_id);
  return { ...state, progress: fresh.progress, rep: fresh.rep, cursors: { ...state.cursors, progress: null }, version: state.version + 1 };
}

/** The type arrived after readings without one: nothing is reset, but the last progress cursor would skip the first reading under it. */
export function clearProgressCursor(state: StateLike): StateLike {
  return { ...state, cursors: { ...state.cursors, progress: null } };
}
