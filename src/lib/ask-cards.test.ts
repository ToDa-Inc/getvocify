import assert from "node:assert/strict";
import test from "node:test";
import { askCards, citedPlaybook, pointsChange } from "./ask-cards.ts";
import { messagesFromTurns, reduceThread, emptyThread, type AskAction } from "./ask-thread.ts";

const focus = {
  step_id: "s1", label: "Confirmar problema", criterion: "Nombra el problema", example: "",
  why: { rate: 0.25, applicable: 8, missing: 6, peer_median: 0.7 },
  progress: [], week_total: { done: 2, applicable: 5, rate: 0.4 }, achieved: false,
};

test("a coaching card keeps the Coach screen's rates, clamped, and drops steps without a name", () => {
  const [card] = askCards({
    cards: [{ kind: "coaching", flow: "sdr", focus, steps: [{ step_id: "s1", label: "Confirmar problema", rate: 1.4, prev_rate: null, peer_median: 0.7 }, { step_id: "s2", label: " " }], conversion: null }],
  });
  assert.equal(card.kind, "coaching");
  assert.ok(card.kind === "coaching" && card.steps.length === 1 && card.steps[0].rate === 1 && card.focus?.label === "Confirmar problema");
});

test("unknown kinds and empty cards are dropped, never drawn half-empty", () => {
  assert.deepEqual(askCards({ cards: [{ kind: "chart" }, { kind: "coaching", steps: [] }, { kind: "team", process: [], reps: [] }, null] }), []);
  assert.deepEqual(askCards({ cards: "nope" }), []);
});

test("a team card keeps the verdicts and reps it was given", () => {
  const [card] = askCards({
    cards: [{ kind: "team", period: "week", adherence: 0.62, previous: 0.5, process: [{ motion: "discovery", verdict: "coach_reps", scored: 40 }], reps: [{ name: "Abel", focus: null }, { name: "" }], more_reps: 0 }],
  });
  assert.ok(card.kind === "team" && card.reps.length === 1 && card.process[0].verdict === "coach_reps");
  assert.equal(pointsChange(0.62, 0.5), 12);
  assert.equal(pointsChange(0.62, null), null);
});

test("cards ride on the final event and come back on a reload", () => {
  const cards = [{ kind: "coaching", flow: "sdr", focus, steps: [], conversion: null }];
  const actions: AskAction[] = [
    { type: "send", id: "a", text: "¿qué mejoro?" },
    { type: "event", event: { type: "final", text: "Tu foco es confirmar el problema.", evidence: [], cards } as never },
  ];
  const thread = actions.reduce(reduceThread, emptyThread());
  assert.equal(thread.messages[1].cards.length, 1);
  const restored = messagesFromTurns([{ turn_id: "t1", status: "completed", text: "x", question: "q", cards }]);
  assert.equal(restored[1].cards[0].kind, "coaching");
});

test("only the playbook's approved answers count as playbook sources", () => {
  const cited = citedPlaybook([{ id: "ev-1", speaker: "prospect" }, { id: "pb-1", speaker: "playbook" }]);
  assert.deepEqual(cited.map((e) => e.id), ["pb-1"]);
});
