import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  applyPoints, applyProgress, applyRewrite, dismissPoint, emptyLiveState, openPoints, pointsIn, progressIn, tick, unansweredPoints, untick,
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

describe("go deeper and versions", () => {
  it("a deepen point is a point like any other: its words are its first version", () => {
    const state = applyPoints(emptyLiveState(), pointsResult([example.deepen_point]));
    assert.equal(state.points[0].kind, "deepen");
    assert.deepEqual(state.points[0].versions, ["¿Cuántas horas a la semana se os van en meterlo en el CRM?"]);
    assert.deepEqual(state.points[0].turn_ids, ["t8"]);
  });

  it("a point still being read has no version until its words are written", () => {
    let state = applyPoints(emptyLiveState(), pointsResult([point({ answer: null, fallback: null })]));
    assert.deepEqual(state.points[0].versions, []);
    state = applyPoints(state, pointsResult([{ id: "pt-1", is_update: true, turn_ids: ["t1"], repeated: false, fallback: "Lo confirmo y te digo." }]));
    assert.deepEqual(state.points[0].versions, ["Lo confirmo y te digo."]);
  });

  it("a rewrite is appended once; an empty one, an unknown point or a point still being read change nothing", () => {
    let state = applyPoints(emptyLiveState(), example.points_result);
    const { rewrite } = example.rewrite_result;
    state = applyRewrite(state, rewrite);
    assert.deepEqual(state.points[0].versions, [example.points_result.points[0].answer, rewrite.answer]);
    assert.equal(applyRewrite(state, rewrite), state);
    assert.equal(applyRewrite(state, { ...rewrite, answer: "  " }), state);
    assert.equal(applyRewrite(state, null), state);
    assert.equal(applyRewrite(state, { ...rewrite, point_id: "pt-nope" }), state);
    const reading = applyPoints(emptyLiveState(), pointsResult([point({ answer: null, fallback: null })]));
    assert.equal(applyRewrite(reading, { point_id: "pt-1", version: 0, answer: "Algo." }), reading);
    // Text on screen is never replaced: a later reading's words do not touch the versions.
    state = applyPoints(state, pointsResult([{ ...example.points_result.points[0], answer: "Otra." }]));
    assert.equal(state.points[0].versions.length, 2);
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

  it("a step with parts: parts heard accumulate, the step is done once enough are heard", () => {
    let state = applyProgress(emptyLiveState(), example.progress_result);
    assert.ok(!state.progress.steps.cualificar_el_encaje);
    assert.deepEqual(state.progress.parts.cualificar_el_encaje, { crm_que_usan: { quote: "usamos Salesforce" } });
    assert.deepEqual(state.progress.part_lists.cualificar_el_encaje.need, 3);
    assert.deepEqual(state.progress.part_lists.cualificar_el_encaje.parts.map((p) => p.id), ["crm_que_usan", "visitas_al_dia", "quien_decide"]);
    const step = example.progress_result.steps[1];
    const heard = (ids) => ({ ...step, parts: step.parts.map((p) => ({ ...p, done: ids.includes(p.id), quote: ids.includes(p.id) ? `q ${p.id}` : null })) });
    // A later reading that does not hear the CRM again does not undo it.
    state = applyProgress(state, { ...example.progress_result, state_version: 4, steps: [heard(["visitas_al_dia"])] });
    assert.ok(!state.progress.steps.cualificar_el_encaje);
    assert.deepEqual(Object.keys(state.progress.parts.cualificar_el_encaje), ["crm_que_usan", "visitas_al_dia"]);
    state = applyProgress(state, { ...example.progress_result, state_version: 5, steps: [heard(["quien_decide"])] });
    const done = state.progress.steps.cualificar_el_encaje;
    assert.deepEqual([done.status, done.by, done.need], ["done", "brain", 3]);
    assert.deepEqual(done.parts.map((p) => [p.id, p.done, p.quote]), [
      ["crm_que_usan", true, "usamos Salesforce"], ["visitas_al_dia", true, "q visitas_al_dia"], ["quien_decide", true, "q quien_decide"],
    ]);
    assert.deepEqual(progressIn(state).done_steps, ["apertura_con_marco", "cualificar_el_encaje"]);
  });

  it("the rep's untick of a step with parts is final even when its parts are heard", () => {
    let state = untick(emptyLiveState(), "cualificar_el_encaje", "step");
    const step = example.progress_result.steps[1];
    state = applyProgress(state, { ...example.progress_result, steps: [{ ...step, status: "done", parts: step.parts.map((p) => ({ ...p, done: true })) }] });
    assert.ok(!state.progress.steps.cualificar_el_encaje);
    assert.equal(Object.keys(state.progress.parts.cualificar_el_encaje).length, 3);
  });

  it("reads a state written before parts existed", () => {
    const old = emptyLiveState();
    delete old.progress.parts;
    delete old.progress.part_lists;
    assert.ok(applyProgress(old, example.progress_result).progress.parts.cualificar_el_encaje);
  });

  it("a skipped reading changes nothing but the cursor", () => {
    let state = applyProgress(emptyLiveState(), example.progress_result);
    const before = state.progress;
    state = applyProgress(state, { producer: "progress", state_version: 9, cursor: "t8:3", skipped: "no_new_words", steps: [], data: [] });
    assert.equal(state.progress.now, before.now);
    assert.equal(state.cursors.progress, "t8:3");
  });
});
