import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  applyPoints, applyProgress, dismissPoint, emptyLiveState, openPoints, pointsIn, progressIn, tick, unansweredPoints, untick,
} from "./state.js";

const example = JSON.parse(readFileSync(new URL("./example.json", import.meta.url), "utf8"));
const point = (patch = {}) => ({
  id: "pt-1", is_update: false, kind: "question", tag_key: "question", tag: null, title: "¿cuánto cuesta?", turn_ids: ["t1"],
  said_at: 10, repeated: false, outcome: "open", decision: "responder", decision_note: null, answer: "Son 30 € al mes.",
  fallback: null, gap: null, source: { id: "knowledge", label: "Company knowledge" }, ...patch,
});
const pointsResult = (points, rest = {}) => ({ producer: "points", state_version: 0, cursor: "t1:5", points, closed: [], ...rest });

describe("points", () => {
  it("takes the example result as it is", () => {
    const state = applyPoints(emptyLiveState("c1"), example.points_result);
    assert.equal(state.points.length, 2); // the update names a point this state does not have
    assert.equal(state.points[0].read_version, 3);
    assert.equal(state.cursors.points, "t7:58");
    assert.equal(state.version, 1);
  });

  it("never duplicates a point: the same id is the same point", () => {
    let state = applyPoints(emptyLiveState(), pointsResult([point()]));
    state = applyPoints(state, pointsResult([point({ answer: "Otra cosa." })]));
    assert.equal(state.points.length, 1);
    assert.equal(state.points[0].answer, "Son 30 € al mes."); // text on screen is never replaced
  });

  it("an update of a point still being read writes its words once", () => {
    let state = applyPoints(emptyLiveState(), pointsResult([point({ answer: null, fallback: null })]));
    state = applyPoints(state, pointsResult([{ id: "pt-1", is_update: true, turn_ids: ["t1"], repeated: false, answer: "Son 30 €.", source: null }]));
    assert.equal(state.points[0].answer, "Son 30 €.");
    state = applyPoints(state, pointsResult([{ id: "pt-1", is_update: true, turn_ids: ["t1"], repeated: false, answer: "Otra." }]));
    assert.equal(state.points[0].answer, "Son 30 €.");
  });

  it("a repeat reopens the same point; the rep's X stays unless Responder asked", () => {
    let state = applyPoints(emptyLiveState(), pointsResult([point()], { closed: [] }));
    state = applyPoints(state, pointsResult([], { closed: [{ id: "pt-1", outcome: "answered" }] }));
    assert.equal(state.points[0].outcome, "answered");
    const again = pointsResult([{ id: "pt-1", is_update: true, turn_ids: ["t9"], repeated: true }]);
    state = applyPoints(state, again);
    assert.deepEqual([state.points[0].outcome, state.points[0].repeated, state.points[0].turn_ids], ["open", true, ["t1", "t9"]]);
    state = dismissPoint(state, "pt-1");
    assert.equal(applyPoints(state, again).points[0].outcome, "dismissed");
    assert.equal(applyPoints(state, again, { asked: true }).points[0].outcome, "open");
  });

  it("outcomes: final ones stay, unanswered can still become answered, the X is never overwritten", () => {
    let state = applyPoints(emptyLiveState(), pointsResult([point(), point({ id: "pt-2", turn_ids: ["t2"] })]));
    state = applyPoints(state, pointsResult([], { closed: [{ id: "pt-1", outcome: "unanswered" }, { id: "pt-2", outcome: "promised" }] }));
    assert.deepEqual(unansweredPoints(state).map((p) => p.id), ["pt-1"]);
    state = applyPoints(state, pointsResult([], { closed: [{ id: "pt-1", outcome: "answered" }, { id: "pt-2", outcome: "unanswered" }] }));
    assert.deepEqual(state.points.map((p) => p.outcome), ["answered", "promised"]);
    state = dismissPoint(applyPoints(emptyLiveState(), pointsResult([point()])), "pt-1");
    assert.equal(applyPoints(state, pointsResult([], { closed: [{ id: "pt-1", outcome: "answered" }] })).points[0].outcome, "dismissed");
    assert.equal(openPoints(state).length, 0);
  });

  it("pointsIn sends the open points and the last closed ones, with what was shown", () => {
    const state = applyPoints(emptyLiveState(), pointsResult([point(), point({ id: "pt-2", outcome: "answered" })]));
    assert.deepEqual(pointsIn(state).map((p) => p.id), ["pt-2", "pt-1"]);
    assert.equal(pointsIn(state)[1].say, "Son 30 € al mes.");
  });
});

describe("progress", () => {
  it("takes the example result: evidence by id, the stable now, the brain's picks", () => {
    const state = applyProgress(emptyLiveState(), example.progress_result);
    assert.equal(state.progress.steps.apertura_con_marco.quote, "soy Toni, fundador de Vocify");
    assert.equal(state.progress.data.crm_que_usan.by, "brain");
    assert.equal(state.progress.now.id, "plantear_el_problema");
    assert.deepEqual(state.progress.missing, ["plantear_el_problema", "volumen_de_interacciones"]);
    assert.deepEqual(progressIn(state).done_steps, ["apertura_con_marco"]);
  });

  it("evidence only accumulates: a later reading never undoes a done step", () => {
    let state = applyProgress(emptyLiveState(), example.progress_result);
    state = applyProgress(state, { ...example.progress_result, state_version: 4, steps: [], data: [], now: null, missing: [] });
    assert.ok(state.progress.steps.apertura_con_marco);
    assert.equal(state.progress.now, null);
  });

  it("a late result adds evidence but does not move now or the picks", () => {
    let state = applyProgress(emptyLiveState(), { ...example.progress_result, state_version: 5 });
    const late = { ...example.progress_result, state_version: 2, steps: [{ id: "otro", status: "done", quote: "x", turn_ids: [] }], now: { kind: "step", id: "viejo", say: null }, missing: ["viejo"] };
    state = applyProgress(state, late);
    assert.ok(state.progress.steps.otro);
    assert.equal(state.progress.now.id, "plantear_el_problema");
  });

  it("the rep's tick is final; unticking moves it back and the brain does not tick it again", () => {
    let state = applyProgress(emptyLiveState(), example.progress_result);
    state = tick(state, "plantear_el_problema", "step");
    assert.deepEqual([state.progress.steps.plantear_el_problema.by, state.progress.steps.plantear_el_problema.quote], ["rep", null]);
    assert.equal(state.progress.now, null);
    assert.ok(!state.progress.missing.includes("plantear_el_problema"));
    const brainTicks = { ...example.progress_result, steps: [{ id: "plantear_el_problema", status: "done", quote: "algo", turn_ids: ["t3"] }] };
    assert.equal(applyProgress(state, brainTicks).progress.steps.plantear_el_problema.by, "rep");
    state = untick(state, "plantear_el_problema", "step");
    assert.ok(!state.progress.steps.plantear_el_problema);
    assert.ok(!applyProgress(state, brainTicks).progress.steps.plantear_el_problema);
    state = untick(state, "apertura_con_marco", "step"); // something the brain had ticked
    assert.ok(!applyProgress(state, example.progress_result).progress.steps.apertura_con_marco);
  });

  it("a skipped reading changes nothing but the cursor", () => {
    let state = applyProgress(emptyLiveState(), example.progress_result);
    const before = state.progress;
    state = applyProgress(state, { producer: "progress", state_version: 9, cursor: "t8:3", skipped: "no_new_words", steps: [], data: [] });
    assert.equal(state.progress.now, before.now);
    assert.equal(state.cursors.progress, "t8:3");
  });
});
