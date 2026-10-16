// The dashboard side of the live call assistant's brain (spec 2026-10-16-live-call-assistant-design.md): what a reading
// sends, when a reading happens, how a stream of tokens becomes a draft, and what the views draw from the state. Pure: the
// hook (features/desktop/assist/useLiveBrain.ts) does the I/O. The state and its merging are shared/live-call/state.js.
//
// No `@/` imports: this file runs under node --test.
import type { MeetingDisplayTurn } from "./meeting-transcript.ts";
import { emptyLiveState, pointsIn, progressIn } from "../../shared/live-call/state.js";

/** Why a reading happens: the checkpoint, or the rep asking (the wire's `reason`). */
export type LiveReason = "turn_end" | "long_turn" | "rep_turn" | "responder" | "preguntar" | "resumen";
export const ASKED_REASONS: readonly LiveReason[] = ["responder", "preguntar", "resumen"];

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
  if (reason === "resumen" || reason === "preguntar") return null;
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
}): Record<string, unknown> {
  const { call, state, reason } = input;
  const points = pointsIn(state).slice(-24).map((point) => ({ ...point, say: point.say ? point.say.slice(0, 400) : null }));
  const focus = focusFor(reason, input.turns, input.mark ?? null);
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
  };
}

// ---------- the points stream ----------

export type StreamedPoint = { title: string | null; say: string | null; grounded: boolean | null };

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
      title: partialString(chunk, "quote")?.trim() || null,
      say: partialString(chunk, "say")?.trim() || null,
      grounded: grounded ? grounded[1] === "true" : null,
    };
  });
}

// ---------- the playbook's words for the ids ----------

export type PlaybookStep = { id: string; label: string; criterion: string; example: string | null; concept: string | null; live: boolean };
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

/** The playbook of the call's type as the views draw it: the editor's steps and criteria, with the producer's aids. */
export function playbookView(input: {
  key: string | null;
  name: string | null;
  hasPlaybook: boolean;
  editor: EditorLike;
  aids: AidsLike;
}): PlaybookView {
  const { editor, aids } = input;
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
export type LiveBrainAsks = {
  responder: null | { seq: number; status: "reading" | "found" | "nothing"; point_id: string | null };
  recap: null | { seq: number; status: "reading" | "ready"; up_to_t: number | null; lines: string[]; unknown: string[] };
};

/** The whole payload of shell.setState({ liveBrain }) (see the contract note live-state-shell-contract.md). */
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
}) {
  return {
    on: input.on,
    call_id: input.callId,
    state: input.state,
    playbook: input.playbook,
    reading: input.reading,
    offline_since: input.offlineSince,
    drafts: input.drafts,
    asks: input.asks,
    type_changed: input.typeChanged,
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
