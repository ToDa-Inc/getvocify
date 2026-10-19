// The live call assistant's state (spec 2026-10-16-live-call-assistant-design.md, "Backend: one brain").
//
// The renderer holds this state and pushes it to the island; the backend's two producers are stateless (they get the call and
// the part of this state they need, `pointsIn` / `progressIn`) and what they return is merged here. Names are the wire's
// (snake_case): backend/app/services/copilot/live_models.py is the other side of this file, and example.json is read by a
// test on each side.
//
// Merging rules (the spec's "Concurrency"): a result carries the state version it read; a late result is merged by id and
// never replaces newer data. Evidence only accumulates: a done step stays done unless the rep unticks it. The rep's marks
// are final: the brain never unticks or re-ticks them. Text on screen is never replaced: a point that already has its
// words keeps them.

/** @typedef {"question" | "objection" | "deepen"} PointKind   "deepen": a question to go deeper on something they said. */
/** @typedef {"responder" | "reconducir" | "aplazar" | "cerrar"} Decision */
/** @typedef {"open" | "answered" | "promised" | "unanswered" | "gone" | "dismissed"} Outcome */

/**
 * @typedef {Object} LivePoint
 * @property {string} id                Stable: the same thing said, from the same stretch of the call.
 * @property {PointKind} kind
 * @property {string} tag_key           "question", an objection type, or a playbook entry's id.
 * @property {string | null} tag        The playbook entry's name when the tag is one; else null (the UI names the kind).
 * @property {string} title             Their words, verbatim, short.
 * @property {string[]} turn_ids        The turns it comes from.
 * @property {number} said_at           Seconds into the call.
 * @property {Decision | null} decision Null when there is no state or playbook to justify one: only the answer.
 * @property {string | null} decision_note
 * @property {string | null} answer     What to say, when every claim in it is written in a source.
 * @property {string | null} fallback   The honest line to say when the fact is not in the company's knowledge.
 * @property {string[]} versions        What to say, every version: [answer or fallback, ...rewrites]; [] while it is read.
 *                                      The version shown is the island's choice (it cycles), not kept here.
 * @property {string | null} gap        What is not written (shown as "No está en tu conocimiento" + this).
 * @property {{id: string, label: string} | null} source
 * @property {boolean} repeated         They came back to it ("Lo repite").
 * @property {Outcome} outcome
 * @property {number} read_version      The state version this point was last written at.
 */

/**
 * @typedef {Object} LiveStep
 * @property {string} id
 * @property {"done"} status
 * @property {"brain" | "rep"} by       "rep": ticked by hand, no evidence: coaching never treats it as proven.
 * @property {string | null} quote
 * @property {string[]} turn_ids
 * @property {{id: string, label: string, done: boolean, quote: string | null}[]} [parts]   A step whose criterion lists parts.
 * @property {number} [need]            How many of its parts make it done.
 */

/**
 * @typedef {Object} LiveData
 * @property {string} id                The qualification criterion's id.
 * @property {string | null} value
 * @property {string | null} quote
 * @property {string[]} turn_ids
 * @property {boolean} reread           Read again under a new playbook after a type change.
 * @property {"brain" | "rep"} by
 */

/**
 * @typedef {Object} LiveProgress
 * @property {{key: string | null, name: string | null} | null} playbook
 * @property {boolean} has_playbook
 * @property {Object<string, LiveStep>} steps
 * @property {Object<string, LiveData>} data
 * @property {{reached: true, value: string | null, quote: string | null, turn_ids: string[], by: "brain" | "rep"} | null} goal
 * @property {{kind: "step" | "data" | "goal", id: string, say: string | null} | null} now   Ahora: stable between readings.
 * @property {string[]} missing         The brain's picks, most important first.
 * @property {{steps: Object, data: Object} | null} aids   A few words per step, a question per data point, which steps are coaching only.
 * @property {Object<string, Object<string, {quote: string | null, by?: "rep"}>>} parts   Parts heard per step, with the words.
 *                                      Only accumulates.
 * @property {Object<string, {parts: {id: string, label: string}[], need: number}>} part_lists   The parts each step lists (from
 *                                      the producer: generated once per published playbook version).
 * @property {number} read_version
 */

/**
 * @typedef {Object} LiveState
 * @property {number} version
 * @property {string} call_id
 * @property {LivePoint[]} points       Oldest first.
 * @property {LiveProgress} progress
 * @property {{ticked: string[], unticked: string[]}} rep   The rep's marks: final.
 * @property {{points: string | null, progress: string | null}} cursors   The last result's cursor per producer.
 */

const TERMINAL = new Set(["answered", "promised", "gone", "dismissed"]);
const RECENT_CLOSED = 8;

/** @returns {LiveState} */
export function emptyLiveState(callId = "") {
  return {
    version: 0,
    call_id: callId,
    points: [],
    progress: {
      playbook: null, has_playbook: false, steps: {}, data: {}, goal: null, now: null, missing: [], aids: null, parts: {}, part_lists: {},
      read_version: -1,
    },
    rep: { ticked: [], unticked: [] },
    cursors: { points: null, progress: null },
  };
}

const bump = (state, patch) => ({ ...state, ...patch, version: state.version + 1 });
const union = (a, b) => [...new Set([...(a ?? []), ...(b ?? [])])];
const words = (point) => (point.answer ?? point.fallback ?? "").trim();

/** An outcome the brain writes: only from open or unanswered, never over the rep's X or a final one. */
function closing(point, outcome) {
  if (point.outcome === "dismissed") return point.outcome;
  if (point.outcome === "open") return outcome;
  if (point.outcome === "unanswered" && outcome !== "unanswered") return outcome;
  return point.outcome;
}

/**
 * Merges a points result (see the points producer's `result` event). `asked`: the rep tapped Responder, so a point they
 * had closed (even with the X) comes back.
 * @param {LiveState} state
 * @param {Object} result
 * @param {{asked?: boolean}} [options]
 * @returns {LiveState}
 */
export function applyPoints(state, result, { asked = false } = {}) {
  const readAt = Number.isFinite(result.state_version) ? result.state_version : state.version;
  let points = state.points;
  for (const incoming of result.points ?? []) {
    const at = points.findIndex((p) => p.id === incoming.id);
    if (at < 0) {
      if (incoming.is_update) continue; // an update of a point this state does not have: nothing to update
      const { is_update: _isUpdate, ...fresh } = incoming;
      points = [...points, { ...fresh, versions: words(fresh) ? [words(fresh)] : [], read_version: readAt }];
      continue;
    }
    const current = points[at];
    const wrote = Boolean(words(current));
    const reopens = incoming.repeated && (current.outcome !== "dismissed" || asked);
    const merged = {
      ...current,
      turn_ids: union(current.turn_ids, incoming.turn_ids),
      repeated: current.repeated || Boolean(incoming.repeated),
      outcome: reopens || (asked && current.outcome !== "open") ? "open" : current.outcome,
    };
    if (!wrote && (incoming.answer ?? incoming.fallback)) {
      // Its words were still being read: the first reading to write them wins. Text on screen is never replaced.
      for (const key of ["decision", "decision_note", "answer", "fallback", "gap", "source"]) merged[key] = incoming[key] ?? null;
      merged.versions = [words(merged)];
      merged.read_version = readAt;
    }
    points = points.map((p, i) => (i === at ? merged : p));
  }
  for (const done of result.closed ?? []) {
    points = points.map((p) => (p.id === done.id ? { ...p, outcome: closing(p, done.outcome) } : p));
  }
  return bump(state, { points, cursors: { ...state.cursors, points: result.cursor ?? state.cursors.points } });
}

/**
 * Another version of a point's words (Responder pressed on a card already on screen: the same source, another angle). It is
 * appended; a point still being read, an empty rewrite or one already there change nothing.
 * @param {LiveState} state
 * @param {{point_id: string, version?: number, answer: string | null} | null} rewrite
 * @returns {LiveState}
 */
export function applyRewrite(state, rewrite) {
  const text = (rewrite?.answer ?? "").trim();
  const point = text ? state.points.find((p) => p.id === rewrite.point_id) : null;
  const versions = point?.versions ?? [];
  if (!point || !versions.length || versions.includes(text)) return state;
  return bump(state, { points: state.points.map((p) => (p === point ? { ...p, versions: [...versions, text] } : p)) });
}

/** The X on a point: it ends as Descartado (logged to improve detection). */
export function dismissPoint(state, id) {
  return bump(state, { points: state.points.map((p) => (p.id === id ? { ...p, outcome: "dismissed" } : p)) });
}

/**
 * Merges a progress result. Evidence accumulates; the rep's marks win; `now` and `missing` follow the newest reading only.
 * A step with parts comes as `{id, status: "open" | "done", parts: [{id, label, done, quote}], need}`.
 * @param {LiveState} state
 * @param {Object} result
 * @returns {LiveState}
 */
export function applyProgress(state, result) {
  const readAt = Number.isFinite(result.state_version) ? result.state_version : state.version;
  const old = state.progress;
  const mine = new Set([...state.rep.ticked, ...state.rep.unticked]);
  const steps = { ...old.steps };
  const parts = { ...(old.parts ?? {}) };
  const partLists = { ...(old.part_lists ?? {}) };
  for (const step of result.steps ?? []) {
    const { parts: listed, need, ...rest } = step;
    if (Array.isArray(listed) && listed.length) {
      // A step with parts: what it lists, and the parts heard (with evidence) added to what was heard before.
      partLists[step.id] = { parts: listed.map(({ id, label }) => ({ id, label })), need: Math.max(1, Math.min(listed.length, need ?? listed.length)) };
      const heard = { ...(parts[step.id] ?? {}) };
      for (const part of listed) if (part.done && !heard[part.id]) heard[part.id] = { quote: part.quote ?? null };
      parts[step.id] = heard;
    }
    // Only a step the producer calls done is done; an "open" one (a step with parts, not enough heard) brings its parts.
    if (step.status === "done" && !mine.has(step.id) && !steps[step.id]) steps[step.id] = { ...rest, by: "brain" };
  }
  for (const [id, list] of Object.entries(partLists)) {
    // A done step carries its parts as they stand: done only accumulates.
    if (steps[id]?.by === "brain") {
      const heard = parts[id] ?? {};
      steps[id] = {
        ...steps[id],
        parts: list.parts.map(({ id: part, label }) => ({ id: part, label, done: Boolean(heard[part]), quote: heard[part]?.quote ?? null })),
        need: list.need,
      };
    }
  }
  const data = { ...old.data };
  for (const item of result.data ?? []) if (!mine.has(item.id) && !data[item.id]) data[item.id] = { ...item, by: "brain" };
  const goal = old.goal ?? (result.goal && !mine.has("goal") ? { ...result.goal, by: "brain" } : null);
  const newest = readAt >= old.read_version && !result.skipped;
  const progress = {
    ...old,
    playbook: result.playbook ?? old.playbook,
    has_playbook: result.has_playbook ?? old.has_playbook,
    steps, data, goal,
    parts, part_lists: partLists,
    aids: result.aids ?? old.aids,
    ...(newest ? { now: result.now ?? null, missing: result.missing ?? [], read_version: readAt } : {}),
  };
  return bump(state, { progress, cursors: { ...state.cursors, progress: result.cursor ?? state.cursors.progress } });
}

/** The rep ticks a step, a data point or the goal by hand: done, final, and without evidence. */
export function tick(state, id, kind) {
  const rep = { ticked: union(state.rep.ticked, [id]), unticked: state.rep.unticked.filter((x) => x !== id) };
  const mark = { status: "done", by: "rep", quote: null, turn_ids: [] };
  const progress = { ...state.progress };
  if (kind === "step") progress.steps = { ...progress.steps, [id]: { id, ...mark } };
  else if (kind === "data") progress.data = { ...progress.data, [id]: { id, value: null, reread: false, ...mark } };
  else progress.goal = { reached: true, value: null, ...mark };
  progress.missing = progress.missing.filter((x) => x !== id);
  if (progress.now?.id === id) progress.now = null;
  return bump(state, { rep, progress });
}

/** The rep unticks: back to Falta. Whatever the brain had ticked stays unticked (the rep's action is final). */
export function untick(state, id, kind) {
  const rep = { ticked: state.rep.ticked.filter((x) => x !== id), unticked: union(state.rep.unticked, [id]) };
  const progress = { ...state.progress };
  if (kind === "step") progress.steps = Object.fromEntries(Object.entries(progress.steps).filter(([k]) => k !== id));
  else if (kind === "data") progress.data = Object.fromEntries(Object.entries(progress.data).filter(([k]) => k !== id));
  else progress.goal = null;
  return bump(state, { rep, progress });
}

/** The open and recent points a producer needs to update instead of duplicating. */
export function pointsIn(state) {
  const open = state.points.filter((p) => !TERMINAL.has(p.outcome));
  const recent = state.points.filter((p) => TERMINAL.has(p.outcome)).slice(-RECENT_CLOSED);
  return [...recent, ...open].map((p) => ({
    id: p.id, kind: p.kind, tag_key: p.tag_key, title: p.title, turn_ids: p.turn_ids, outcome: p.outcome,
    say: p.answer ?? p.fallback ?? null,
    // What the rewrite reads: where the words came from (none: an unknown, the rewrite is a question back) and what was seen.
    source_id: p.source?.id ?? null,
    versions: p.versions ?? [],
  }));
}

/** What the progress producer and the points producer read of the playbook's progress. */
export function progressIn(state) {
  const { progress, rep } = state;
  return {
    done_steps: Object.keys(progress.steps),
    known_data: Object.keys(progress.data),
    goal_reached: Boolean(progress.goal),
    rep_ticked: rep.ticked,
    rep_unticked: rep.unticked,
    now: progress.now,
    missing: progress.missing,
    // The parts heard so far, per step.
    parts: Object.fromEntries(Object.entries(progress.parts ?? {}).map(([id, heard]) => [id, Object.keys(heard)])),
  };
}

/** Points the rep has not dealt with (open, or ended without an answer): the Ayuda tab's count and the bar's chip. */
export const openPoints = (state) => state.points.filter((p) => p.outcome === "open");
export const unansweredPoints = (state) => state.points.filter((p) => p.outcome === "unanswered");
