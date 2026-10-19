/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildReading,
  clearProgressCursor,
  contactBrief,
  nextAsk,
  turnsUpTo,
  focusFor,
  liveBrainPayload,
  resetForType,
  longTurnDue,
  playbookView,
  pointSays,
  pointsView,
  progressView,
  repReadingDue,
  repWords,
  streamedPoints,
  toWireTurns,
  LONG_TURN_MS,
  MAX_TURNS,
  REP_GAP_MS,
  REP_WORDS,
} from "./live-brain.ts";
import { meetingDisplayTurns, meetingOverlay, type MeetingDisplayTurn } from "./meeting-transcript.ts";
import { applyPoints, applyProgress, applyRewrite, dismissPoint, emptyLiveState, tick, untick } from "../../shared/live-call/state.js";

const example = JSON.parse(readFileSync(new URL("../../shared/live-call/example.json", import.meta.url), "utf8"));

const turn = (key: string, speaker: "rep" | "prospect" | null, text: string, start = 0, extra: Partial<MeetingDisplayTurn> = {}): MeetingDisplayTurn => ({
  key, speaker, label: null, text, pending: "", start, ...extra,
});
const call = { callId: "c1", callMode: "meeting" as const, typeKey: "discovery", typeLabel: "Llamada en frío" };

const editor = {
  steps: [
    { step_id: "apertura_con_marco", label: "Apertura con marco", criterion: "Se presenta y fija el marco", example: "Soy Toni, serán dos minutos." },
    { step_id: "plantear_el_problema", label: "Plantear el problema", criterion: "Nombra el dolor", example: "El CRM se deja para luego." },
    { step_id: "explicar_vocify", label: "Explicar Vocify en 30 segundos", criterion: "Habla claro" },
  ],
  qualification: [
    { criterion_id: "crm_que_usan", label: "CRM que usan", good: "Nombra el CRM" },
    { criterion_id: "volumen_de_interacciones", label: "Volumen", good: "Cifra por semana" },
  ],
};
const aids = {
  steps: { apertura_con_marco: { concept: "Preséntate y di que será breve", live: true }, explicar_vocify: { concept: "Explica", live: false } },
  data: { crm_que_usan: { question: "¿Qué CRM usáis?" } },
};
const playbook = playbookView({ key: "discovery", name: "Llamada en frío", hasPlaybook: true, editor, aids });

describe("the call as the backend reads it", () => {
  it("sends text, side, name and time, and leaves out a turn with no known side", () => {
    const wire = toWireTurns([
      turn("u1", "rep", "Hola, soy Toni", 1.5),
      turn("u2", "prospect", "Dime", 4, { pending: "rápido", name: "Javier" }),
      turn("u3", null, "ruido", 5),
      turn("u4", "rep", "   ", 6),
    ]);
    assert.deepEqual(wire, [
      { id: "u1", who: "you", text: "Hola, soy Toni", t: 1.5 },
      { id: "u2", who: "them", name: "Javier", text: "Dime rápido", t: 4 },
    ]);
  });

  it("keeps the opening and the latest stretch of a call over the backend's limit", () => {
    const many = Array.from({ length: MAX_TURNS + 50 }, (_, i) => turn(`u${i}`, i % 2 ? "prospect" : "rep", `palabra ${i}`, i));
    const wire = toWireTurns(many);
    assert.equal(wire.length, MAX_TURNS);
    assert.equal(wire[0].id, "u0");
    assert.equal(wire[wire.length - 1].id, `u${MAX_TURNS + 49}`);
  });

  it("counts the rep's words and reads after their turn only when enough are new, and not too soon", () => {
    const turns = [turn("u1", "rep", "uno dos tres cuatro cinco seis siete ocho nueve"), turn("u2", "prospect", "vale")];
    assert.equal(repWords(turns), 9);
    assert.equal(repReadingDue({ words: 9, readWords: 0, lastReadAt: null, now: 1000 }), true);
    assert.equal(repReadingDue({ words: 9, readWords: 5, lastReadAt: null, now: 1000 }), false);
    assert.equal(repReadingDue({ words: REP_WORDS, readWords: 0, lastReadAt: 1000, now: 1000 + REP_GAP_MS - 1 }), false);
    assert.equal(repReadingDue({ words: REP_WORDS, readWords: 0, lastReadAt: 1000, now: 1000 + REP_GAP_MS }), true);
  });

  it("reads a long turn at a breath only every LONG_TURN_MS", () => {
    assert.equal(longTurnDue({ lastReadAt: null, now: 5 }), true);
    assert.equal(longTurnDue({ lastReadAt: 1000, now: 1000 + LONG_TURN_MS - 1 }), false);
    assert.equal(longTurnDue({ lastReadAt: 1000, now: 1000 + LONG_TURN_MS }), true);
  });
});

describe("where a reading's window starts", () => {
  const wire = [0, 20, 40, 70, 100, 130].map((t, i) => ({ id: `t${i}`, who: (i % 2 ? "them" : "you") as "them" | "you", text: "x", t }));
  it("Responder starts about a minute before the tap", () => {
    assert.equal(focusFor("responder", wire, null), "t3"); // 130 - 60 = 70 → the turn at 70
  });
  it("is the whole call when it is shorter than the window", () => {
    assert.equal(focusFor("responder", wire.slice(0, 3), null), "t0");
  });
  it("falls back to the last turns when times are unknown", () => {
    const flat = Array.from({ length: 12 }, (_, i) => ({ id: `f${i}`, who: "them" as const, text: "x", t: 0 }));
    assert.equal(focusFor("responder", flat, null), "f0"); // last t = 0 → within the window → the whole call
  });
  it("an automatic reading starts one turn before what the last one covered", () => {
    assert.equal(focusFor("turn_end", wire, { turnKey: "t3", length: 4 }), "t2");
    assert.equal(focusFor("turn_end", wire, { turnKey: "t0", length: 4 }), "t0");
    assert.equal(focusFor("turn_end", wire, null), null);
    assert.equal(focusFor("turn_end", wire, { turnKey: "gone", length: 1 }), null);
  });
  it("Preguntar and Resumen have no window of their own", () => {
    assert.equal(focusFor("preguntar", wire, null), null);
    assert.equal(focusFor("resumen", wire, null), null);
  });
});

describe("a reading's request", () => {
  const turns = toWireTurns([turn("u1", "rep", "hola", 1), turn("u2", "prospect", "¿se integra con HubSpot?", 3)]);

  it("carries the identities the backend echoes: call, type, version, state in", () => {
    let state = applyPoints(emptyLiveState("c1"), example.points_result);
    state = tick(state, "plantear_el_problema", "step");
    const request = buildReading({ call, turns, state, reason: "turn_end", mark: { turnKey: "u2", length: 5 }, producer: "points" }) as any;
    assert.equal(request.call_id, "c1");
    assert.equal(request.call_mode, "meeting");
    assert.equal(request.sales_motion_key, "discovery");
    assert.equal(request.type_label, "Llamada en frío");
    assert.equal(request.reason, "turn_end");
    assert.equal(request.state_version, state.version);
    assert.equal(request.cursor, "t7:58");
    assert.equal(request.focus_from, "u1");
    assert.deepEqual(request.points.map((p: any) => p.id), ["pt-1a2b3c4d", "pt-9f8e7d6c"]);
    assert.equal(request.points[1].say, "¿Qué proceso os cuesta más hoy con vuestro Salesforce?");
    assert.deepEqual(request.progress.rep_ticked, ["plantear_el_problema"]);
    assert.equal(request.type_changed, undefined);
  });

  it("an asked reading never sends the cursor, so it is never skipped", () => {
    const state = applyPoints(emptyLiveState("c1"), example.points_result);
    const request = buildReading({ call, turns, state, reason: "responder", producer: "points" }) as any;
    assert.equal("cursor" in request, false);
  });

  it("the progress producer sends its own cursor, and says when the type changed", () => {
    let state = applyPoints(emptyLiveState("c1"), example.points_result);
    state = applyProgress(state, { ...example.progress_result, cursor: "t7:99" });
    const request = buildReading({ call, turns, state, reason: "turn_end", producer: "progress", typeChanged: true }) as any;
    assert.equal(request.cursor, "t7:99");
    assert.equal(request.type_changed, true);
  });

  it("the recap reads up to the last turn", () => {
    const request = buildReading({ call, turns, state: emptyLiveState("c1"), reason: "resumen", producer: "recap" }) as any;
    assert.equal(request.up_to, "u2");
  });

  it("a rewrite and a step question carry their target, are asked (no cursor) and have no window of their own", () => {
    const state = applyPoints(emptyLiveState("c1"), example.points_result);
    const rewrite = buildReading({ call, turns, state, reason: "rewrite", producer: "points", target: { point_id: "pt-1a2b3c4d", version: 1 }, sayView: true }) as any;
    assert.deepEqual(rewrite.target, { point_id: "pt-1a2b3c4d", version: 1 });
    assert.equal(rewrite.say_view, true);
    assert.equal("cursor" in rewrite, false);
    assert.equal("focus_from" in rewrite, false);
    const step = buildReading({ call, turns, state, reason: "ask_step", producer: "points", target: { kind: "step", id: "cualificar_el_encaje" } }) as any;
    assert.deepEqual([step.reason, step.target, step.say_view], ["ask_step", { kind: "step", id: "cualificar_el_encaje" }, false]);
  });

  it("Responder about a tapped bubble reads the call up to that bubble, from it", () => {
    const three = toWireTurns([turn("u1", "rep", "hola", 1), turn("u2", "prospect", "mándame un email", 3), turn("u3", "rep", "vale", 5)]);
    const upTo = turnsUpTo(three, "u2")!;
    assert.deepEqual(upTo.map((t) => t.id), ["u1", "u2"]);
    assert.equal(turnsUpTo(three, "nope"), null);
    const request = buildReading({ call, turns: upTo, state: emptyLiveState("c1"), reason: "responder", producer: "points", focusTurn: "u2" }) as any;
    assert.equal(request.focus_from, "u2");
    assert.equal(request.turns.at(-1).id, "u2");
  });

  it("leaves out what is not known", () => {
    const request = buildReading({ call: { callId: "c2", callMode: "softphone" }, turns, state: emptyLiveState("c2"), reason: "turn_end", producer: "points" }) as any;
    for (const key of ["sales_motion_key", "type_label", "contact_id", "focus_from", "cursor", "up_to"]) assert.equal(key in request, false, key);
  });
});

describe("the points stream", () => {
  const full = '{"points": [{"ref": null, "turns": ["t6"], "type": "question", "quote": "¿se integra con HubSpot?", "decision": "responder", "why": "", "grounded": true, "source_id": "knowledge", "gap": "", "say": "Sí, se integra con HubSpot."}], "closed": []}';

  it("reads the quote and the words being written before the JSON is whole", () => {
    assert.deepEqual(streamedPoints('{"points": [{"ref": null, "turns": ["t6"], "type": "question", "quote": "¿se integra'), [
      { title: "¿se integra", say: null, grounded: null },
    ]);
    const cut = full.slice(0, full.indexOf("Sí, se integra") + 8);
    assert.deepEqual(streamedPoints(cut), [{ title: "¿se integra con HubSpot?", say: "Sí, se i", grounded: true }]);
  });

  it("reads the whole answer, with escapes", () => {
    assert.equal(streamedPoints(full)[0].say, "Sí, se integra con HubSpot.");
    const escaped = '{"points": [{"ref": null, "quote": "a \\"b\\"", "say": "línea\\nuno \\u00e9"}]}';
    assert.deepEqual(streamedPoints(escaped), [{ title: 'a "b"', say: "línea\nuno é", grounded: null }]);
    assert.equal(streamedPoints('{"points": [{"ref": null, "say": "cortado \\u00').pop()?.say, "cortado");
  });

  it("separates the points and ignores the closed list", () => {
    const two = '{"points": [{"ref": null, "quote": "uno", "say": "a"}, {"ref": "pt-1", "quote": "dos", "say": "b"}], "closed": [{"id": "pt-9", "outcome": "answered", "why": "quote"}]}';
    assert.deepEqual(streamedPoints(two).map((p) => [p.title, p.say]), [["uno", "a"], ["dos", "b"]]);
    assert.deepEqual(streamedPoints('{"points": []'), []);
    assert.deepEqual(streamedPoints(""), []);
  });
});

describe("the points the views draw", () => {
  const withPoints = () => {
    let state = applyPoints(emptyLiveState("c1"), example.points_result);
    state = applyPoints(state, {
      producer: "points", state_version: 1, cursor: "t9:1", closed: [],
      points: [{ ...example.points_result.points[0], id: "pt-3", title: "¿cuánto cuesta?", answer: "30 € al mes.", is_update: false }],
    });
    return state;
  };

  it("shows the newest two open points in full and the older ones as a line", () => {
    let state = withPoints();
    state = applyPoints(state, { producer: "points", state_version: 2, closed: [], points: [{ ...example.points_result.points[0], id: "pt-4", title: "otra", is_update: false }] });
    const view = pointsView(state.points);
    assert.equal(view.open.length, 4);
    assert.deepEqual([...view.full], ["pt-3", "pt-4"]);
    assert.deepEqual([...pointsView(state.points, new Set(["pt-1a2b3c4d"])).full].sort(), ["pt-1a2b3c4d", "pt-3", "pt-4"]);
  });

  it("puts every point that ended in Antes and counts the ones nobody answered", () => {
    let state = withPoints();
    state = applyPoints(state, { producer: "points", state_version: 3, points: [], closed: [{ id: "pt-3", outcome: "unanswered" }, { id: "pt-1a2b3c4d", outcome: "answered" }] });
    state = dismissPoint(state, "pt-9f8e7d6c");
    const view = pointsView(state.points);
    assert.equal(view.open.length, 0);
    assert.equal(view.before.length, 3);
    assert.equal(view.unanswered, 1);
  });

  it("a question to go deeper is open but does not wait for an answer", () => {
    const state = applyPoints(applyPoints(emptyLiveState("c1"), example.points_result), { ...example.points_result, points: [example.deepen_point] });
    const view = pointsView(state.points);
    assert.equal(view.open.length, 3);
    assert.deepEqual(view.waiting.map((p: any) => p.id), ["pt-1a2b3c4d", "pt-9f8e7d6c"]);
  });

  it("says the answer, else the honest line", () => {
    assert.equal(pointSays({ answer: "Sí.", fallback: null }), "Sí.");
    assert.equal(pointSays({ answer: null, fallback: " Lo confirmo. " }), "Lo confirmo.");
    assert.equal(pointSays({ answer: null, fallback: null }), "");
  });
});

describe("Conversación from the state", () => {
  const read = () => applyProgress(emptyLiveState("c1"), example.progress_result).progress;

  it("draws Ahora, Falta and Hecho from the example result and the playbook's words", () => {
    const view = progressView(read(), playbook, "Cerrar el siguiente paso");
    assert.equal(view.name, "Llamada en frío");
    assert.equal(view.now?.id, "plantear_el_problema");
    assert.equal(view.now?.label, "Plantear el problema");
    assert.equal(view.now?.say, "Lo que vemos en los equipos de campo es que el CRM se deja para luego.");
    assert.deepEqual(view.hecho.map((h) => [h.id, h.detail]), [["apertura_con_marco", "soy Toni, fundador de Vocify"], ["crm_que_usan", "Salesforce"]]);
    // Ahora is drawn once, in Ahora; Falta is the rest: the brain's picks first, then the other unknown data. The
    // delivery-only step is not drawn live.
    assert.deepEqual(view.falta.map((f) => f.id), ["volumen_de_interacciones"]);
    assert.equal(view.falta[0].picked, true);
    assert.equal(view.total, 4); // 2 live steps + 2 data
    assert.equal(view.done, 2);
    assert.equal(view.picks, 2);
  });

  it("a tick by hand is Marcado por ti, final, and moves Ahora on; unticking moves it back", () => {
    let state = applyProgress(emptyLiveState("c1"), example.progress_result);
    state = tick(state, "plantear_el_problema", "step");
    let view = progressView(state.progress, playbook, "Objetivo");
    assert.equal(view.hecho.find((h) => h.id === "plantear_el_problema")?.by, "rep");
    assert.equal(view.hecho.find((h) => h.id === "plantear_el_problema")?.detail, null);
    assert.equal(view.falta.some((f) => f.id === "plantear_el_problema"), false);
    assert.notEqual(view.now?.id, "plantear_el_problema");
    state = untick(state, "plantear_el_problema", "step");
    view = progressView(state.progress, playbook, "Objetivo");
    assert.equal(view.falta.some((f) => f.id === "plantear_el_problema") || view.now?.id === "plantear_el_problema", true);
  });

  it("draws the goal only once the brain has named it", () => {
    const base = read();
    assert.equal(progressView(base, playbook, "Objetivo").falta.some((f) => f.kind === "goal"), false);
    const named = { ...base, missing: [...base.missing, "goal"] };
    const view = progressView(named, playbook, "Objetivo");
    assert.equal(view.falta[view.falta.length - 1].kind, "goal");
    assert.equal(view.total, 5);
  });

  it("with no steps, Ahora is the first unknown data point", () => {
    const noSteps = playbookView({ key: "k", name: "Sin pasos", hasPlaybook: true, editor: { qualification: editor.qualification }, aids });
    const view = progressView(emptyLiveState("c").progress, noSteps, "Objetivo");
    assert.equal(view.noSteps, true);
    assert.equal(view.now?.id, "crm_que_usan");
    assert.equal(view.now?.say, "¿Qué CRM usáis?");
  });

  it("names ids by themselves when the playbook's words could not be read", () => {
    const view = progressView(read(), null, "Objetivo");
    assert.equal(view.hecho[0].label, "Apertura con marco");
    assert.equal(view.now, null); // nothing to say without the playbook... except the brain's own line
  });

  it("no playbook", () => {
    const state = applyProgress(emptyLiveState("c1"), { producer: "progress", state_version: 0, has_playbook: false, playbook: null, steps: [], data: [], goal: null, now: null, missing: [] });
    const view = progressView(state.progress, null, "Objetivo");
    assert.equal(view.hasPlaybook, false);
    assert.equal(view.total, 0);
  });
});

describe("a type change", () => {
  const read = () => {
    let state = applyPoints(emptyLiveState("c1"), example.points_result);
    state = applyProgress(state, example.progress_result);
    return tick(state, "volumen_de_interacciones", "data");
  };

  it("brings the new playbook in as a whole: progress and the rep's marks start over, open points stay", () => {
    const state = resetForType(read());
    assert.deepEqual(state.progress.steps, {});
    assert.deepEqual(state.progress.data, {});
    assert.deepEqual(state.rep, { ticked: [], unticked: [] });
    assert.equal(state.cursors.progress, null);
    assert.equal(state.cursors.points, "t7:58");
    assert.equal(state.points.length, 2);
    assert.equal(state.version, read().version + 1);
  });

  it("a type that arrives after readings without one only clears the progress cursor", () => {
    const before = read();
    const after = clearProgressCursor(before);
    assert.equal(after.cursors.progress, null);
    assert.deepEqual(after.progress, before.progress);
    assert.deepEqual(after.rep, before.rep);
  });
});

describe("what travels to the island", () => {
  it("is plain JSON: the whole state, the playbook's words, the reads and the asks", () => {
    const state = applyProgress(applyPoints(emptyLiveState("c1"), example.points_result), example.progress_result);
    const payload = liveBrainPayload({
      on: true, callId: "c1", state, playbook, reading: { points: true, progress: false, recap: false }, offlineSince: null,
      drafts: [{ title: "¿se integra?", say: "Sí", grounded: true }],
      asks: { responder: { seq: 1, status: "found", point_id: "pt-1a2b3c4d", next: null }, recap: null, step: null, rewrite: null },
      typeChanged: false, view: "tabs", contact: null,
    });
    const wire = JSON.parse(JSON.stringify(payload));
    assert.deepEqual(wire, payload);
    assert.equal(wire.view, "tabs");
    assert.equal(wire.state.points.length, 2);
    assert.equal(wire.playbook.steps[0].concept, "Preséntate y di que será breve");
    assert.equal(wire.playbook.steps.find((s: any) => s.id === "explicar_vocify").live, false);
    assert.equal(wire.contact, null);
  });

  it("the Qué decir view: versions, turn ids, parts heard, the parts each step lists, the asks and the contact (contract §4)", () => {
    let state = applyProgress(applyPoints(emptyLiveState("c1"), example.points_result), example.progress_result);
    state = applyPoints(state, { ...example.points_result, points: [example.deepen_point] });
    state = applyRewrite(state, example.rewrite_result.rewrite);
    const withParts = playbookView({
      key: "discovery", name: "Llamada en frío", hasPlaybook: true,
      editor: { steps: [...editor.steps, { step_id: "cualificar_el_encaje", label: "Cualificar el encaje", criterion: "Al menos tres de estos datos: CRM, visitas, quién decide" }] },
      aids: null, partLists: state.progress.part_lists,
    });
    const asks = {
      responder: { seq: 4, status: "nothing" as const, point_id: null, next: nextAsk(example.responder_nothing_result.next) },
      recap: null,
      step: { seq: 2, kind: "step" as const, id: "cualificar_el_encaje", status: "ready" as const, question: example.step_question_result.step_question.question },
      rewrite: { seq: 3, point_id: "pt-1a2b3c4d", status: "ready" as const },
    };
    const contact = { name: "Marta Ruiz", company: "Distribuciones Norte", first: false, lines: ["Pidió precios en septiembre."] };
    const wire = JSON.parse(JSON.stringify(liveBrainPayload({
      on: true, callId: "c1", state, playbook: withParts, reading: { points: false, progress: false, recap: false }, offlineSince: null,
      drafts: [], asks, typeChanged: false, view: "say", contact,
    })));
    assert.equal(wire.view, "say");
    const [first, , deepen] = wire.state.points;
    assert.deepEqual(first.versions, [example.points_result.points[0].answer, example.rewrite_result.rewrite.answer]);
    assert.deepEqual([deepen.kind, deepen.turn_ids, deepen.versions.length], ["deepen", ["t8"], 1]);
    assert.deepEqual(wire.state.progress.parts.cualificar_el_encaje, { crm_que_usan: { quote: "usamos Salesforce" } });
    const step = wire.playbook.steps.find((s: any) => s.id === "cualificar_el_encaje");
    assert.deepEqual([step.parts.map((p: any) => p.id), step.need], [["crm_que_usan", "visitas_al_dia", "quien_decide"], 3]);
    assert.equal("parts" in wire.playbook.steps[0], false); // only steps whose criterion lists parts
    assert.deepEqual(wire.asks.responder.next, example.responder_nothing_result.next);
    assert.deepEqual(wire.asks.step.question, "¿Cuántas visitas hace cada comercial al día?");
    assert.deepEqual(wire.contact, contact);
  });

  it("the brain's turn ids are the island overlay's bubble ids (the same transcript rows)", () => {
    const transcript = {
      segments: [
        { speaker: "rep" as const, text: "Hola, soy Toni.", start: 0, end: 1 },
        { speaker: "prospect" as const, text: "¿Se integra con HubSpot?", start: 2, end: 3 },
        { speaker: "rep" as const, text: "Sí.", start: 4, end: 5 },
      ],
      interims: { prospect: "y el precio" },
    };
    const brain = toWireTurns(meetingDisplayTurns(transcript as any)).map((t) => t.id);
    const overlay = meetingOverlay(transcript as any).turns.map((t) => t.key);
    assert.deepEqual(brain, overlay);
    assert.equal(brain.length, 4);
  });
});

describe("the contact's brief", () => {
  const read = { emails: "read", notes: "read", calls: "read", meetings: "read", tasks: "read", company: "read" };
  const activity = (patch: Record<string, unknown> = {}) => ({
    company: { name: "Distribuciones Norte" },
    interactions: [{ id: "hubspot:call:1", type: "call", occurred_at: "2026-09-02T10:00:00Z", text: "x" }],
    company_interactions: [],
    summary: { lines: [{ text: "Pidió precios en septiembre.", type: "call", occurred_at: "2026-09-02T10:00:00Z" }], company_lines: [] },
    sources: { hubspot: read, vocify: "read" },
    ...patch,
  });

  it("says only what the activity says: the summary's lines and the company's name", () => {
    assert.deepEqual(contactBrief(" Marta Ruiz ", activity()), { name: "Marta Ruiz", company: "Distribuciones Norte", first: false, lines: ["Pidió precios en septiembre."] });
  });

  it("first contact only when every source was read and nothing happened before", () => {
    const none = { interactions: [], summary: null };
    assert.equal(contactBrief("Marta", activity(none))!.first, true);
    assert.equal(contactBrief("Marta", activity({ ...none, sources: { hubspot: { ...read, emails: "failed" }, vocify: "read" } }))!.first, false);
    assert.equal(contactBrief("Marta", activity({ ...none, sources: { hubspot: read, vocify: "failed" } }))!.first, false);
    assert.equal(contactBrief("Marta", activity({ ...none, sources: undefined }))!.first, false);
  });

  it("while it loads or when it failed: the name alone", () => {
    assert.deepEqual(contactBrief("Marta", null), { name: "Marta", company: null, first: false, lines: [] });
  });

  it("no name, no contact", () => {
    assert.equal(contactBrief(null, activity()), null);
    assert.equal(contactBrief("  ", activity()), null);
  });

  it("the responder's next question only when it is whole", () => {
    assert.deepEqual(nextAsk(example.responder_nothing_result.next), example.responder_nothing_result.next);
    assert.equal(nextAsk({ kind: "data", id: "x", label: "X", question: " " }), null);
    assert.equal(nextAsk(null), null);
  });
});
