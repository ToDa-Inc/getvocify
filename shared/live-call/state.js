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

/** @typedef {"question" | "objection"} PointKind */
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
      playbook: null, has_playbook: false, steps: {}, data: {}, goal: null, now: null, missing: [], aids: null, read_version: -1,
    },
    rep: { ticked: [], unticked: [] },
    cursors: { points: null, progress: null },
  };
}

const bump = (state, patch) => ({ ...state, ...patch, version: state.version + 1 });
const union = (a, b) => [...new Set([...(a ?? []), ...(b ?? [])])];

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
      points = [...points, { ...fresh, read_version: readAt }];
      continue;
    }
    const current = points[at];
    const wrote = Boolean((current.answer ?? current.fallback ?? "").trim());
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
      merged.read_version = readAt;
    }
    points = points.map((p, i) => (i === at ? merged : p));
  }
  for (const done of result.closed ?? []) {
    points = points.map((p) => (p.id === done.id ? { ...p, outcome: closing(p, done.outcome) } : p));
  }
  return bump(state, { points, cursors: { ...state.cursors, points: result.cursor ?? state.cursors.points } });
}

/** The X on a point: it ends as Descartado (logged to improve detection). */
export function dismissPoint(state, id) {
  return bump(state, { points: state.points.map((p) => (p.id === id ? { ...p, outcome: "dismissed" } : p)) });
}

/**
 * Merges a progress result. Evidence accumulates; the rep's marks win; `now` and `missing` follow the newest reading only.
 * @param {LiveState} state
 * @param {Object} result
 * @returns {LiveState}
 */
export function applyProgress(state, result) {
  const readAt = Number.isFinite(result.state_version) ? result.state_version : state.version;
  const old = state.progress;
  const mine = new Set([...state.rep.ticked, ...state.rep.unticked]);
  const steps = { ...old.steps };
  for (const step of result.steps ?? []) if (!mine.has(step.id) && !steps[step.id]) steps[step.id] = { ...step, by: "brain" };
  const data = { ...old.data };
  for (const item of result.data ?? []) if (!mine.has(item.id) && !data[item.id]) data[item.id] = { ...item, by: "brain" };
  const goal = old.goal ?? (result.goal && !mine.has("goal") ? { ...result.goal, by: "brain" } : null);
  const newest = readAt >= old.read_version && !result.skipped;
  const progress = {
    ...old,
    playbook: result.playbook ?? old.playbook,
    has_playbook: result.has_playbook ?? old.has_playbook,
    steps, data, goal,
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
  };
}

/** Points the rep has not dealt with (open, or ended without an answer): the Ayuda tab's count and the bar's chip. */
export const openPoints = (state) => state.points.filter((p) => p.outcome === "open");
export const unansweredPoints = (state) => state.points.filter((p) => p.outcome === "unanswered");
