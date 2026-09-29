import assert from "node:assert/strict";
import test from "node:test";
import { displayText, emptyThread, isBusy, messagesFromTurns, reduceThread, type AskAction } from "./ask-thread.ts";

const run = (actions: AskAction[]) => actions.reduce(reduceThread, emptyThread());
const ev = (event: Record<string, unknown>): AskAction => ({ type: "event", event: event as never });
const last = (t: ReturnType<typeof run>) => t.messages[t.messages.length - 1];

test("send adds the question and an assistant row that is already reserved", () => {
  const t = run([{ type: "send", id: "a", text: "¿Qué pasó?" }]);
  assert.deepEqual(t.messages.map((m) => [m.role, m.phase]), [["user", "done"], ["assistant", "sending"]]);
  assert.equal(isBusy(t), true);
});

test("tools and text arrive in order, then final replaces the raw tokens with numbered evidence", () => {
  const t = run([
    { type: "send", id: "a", text: "q" },
    ev({ type: "turn", turn_id: "t1" }),
    ev({ type: "state", state: "understanding" }),
    ev({ type: "tool_start", call_id: "c1", tool: "deal_story" }),
    ev({ type: "tool_result", call_id: "c1", tool: "deal_story", ok: true, coverage: "partial", n: 3 }),
    ev({ type: "content", delta: "Caro [ev-ab" }),
    ev({ type: "content", delta: "12]." }),
    ev({ type: "final", text: "Caro [1].", evidence: [{ id: "ev-ab12", quote: "caro" }], coverage_note: { level: "partial", n: 3, n_analysed: 1 } }),
    ev({ type: "done", turn_id: "t1", status: "completed" }),
  ]);
  const m = last(t);
  assert.equal(m.phase, "done");
  assert.equal(m.text, "Caro [1].");
  assert.equal(m.turnId, "t1");
  assert.deepEqual(m.steps, [{ id: "c1", tool: "deal_story", status: "ok", coverage: "partial", n: 3 }]);
  assert.equal(m.evidence[0].quote, "caro");
  assert.equal(m.coverageNote?.n_analysed, 1);
  assert.equal(isBusy(t), false);
});

test("raw evidence tokens never show while streaming, even half-typed", () => {
  assert.equal(displayText("Caro [ev-ab12] y luego"), "Caro y luego");
  assert.equal(displayText("Caro [ev-ab"), "Caro");
  assert.equal(displayText("Va [1] bien"), "Va [1] bien");
});

test("content_reset clears the text so a rewrite does not append to the rejected draft", () => {
  const t = run([{ type: "send", id: "a", text: "q" }, ev({ type: "content", delta: "64%" }), ev({ type: "content_reset" }), ev({ type: "content", delta: "9 de 14" })]);
  assert.equal(last(t).text, "9 de 14");
});

test("an error event fails the turn and keeps it retryable unless told otherwise", () => {
  const t = run([{ type: "send", id: "a", text: "q" }, ev({ type: "error", code: "ask_failed", retryable: true })]);
  assert.equal(last(t).phase, "failed");
  assert.equal(last(t).retryable, true);
});

test("losing the connection after the turn arrived keeps it pending, not failed", () => {
  const reached = run([{ type: "send", id: "a", text: "q" }, ev({ type: "turn", turn_id: "t1" }), { type: "connection_lost" }]);
  assert.equal(last(reached).phase, "pending");
  const never = run([{ type: "send", id: "a", text: "q" }, { type: "connection_lost" }]);
  assert.equal(last(never).phase, "failed");
  assert.equal(last(never).retryable, true);
});

test("a completed turn is never downgraded by a late connection_lost", () => {
  const t = run([{ type: "send", id: "a", text: "q" }, ev({ type: "final", text: "ok" }), { type: "connection_lost" }]);
  assert.equal(last(t).phase, "done");
});

test("a snapshot from the persisted turn completes a pending message", () => {
  const t = run([
    { type: "send", id: "a", text: "q" },
    ev({ type: "turn", turn_id: "t1" }),
    { type: "connection_lost" },
    { type: "snapshot", turn: { turn_id: "t1", status: "completed", text: "Listo.", evidence: [], coverage_note: null } },
  ]);
  assert.equal(last(t).phase, "done");
  assert.equal(last(t).text, "Listo.");
});

test("a confirm event becomes a card that follows the real result", () => {
  const t = run([
    { type: "send", id: "a", text: "q" },
    ev({ type: "final", text: "Nota: llamar" }),
    ev({ type: "confirm", operation_id: "op1", revision: 2, contact_id: "c1", summary: "Nota: llamar" }),
  ]);
  assert.equal(last(t).confirm?.status, "proposed");
  const running = reduceThread(t, { type: "confirm_status", status: "running" });
  assert.equal(last(running).confirm?.status, "running");
  const done = reduceThread(running, { type: "confirm_status", status: "succeeded", url: "https://hs/1" });
  assert.equal(last(done).confirm?.url, "https://hs/1");
});

test("history rebuilds question and answer pairs, with an applied write shown as saved", () => {
  const messages = messagesFromTurns([
    { turn_id: "t1", status: "completed", text: "Respuesta", question: "Pregunta", evidence: [{ id: "e", quote: "q" }] },
    { turn_id: "t2", status: "completed", text: "Nota", question: "Crea nota", confirmation: { operation_id: "op", revision: 1, contact_id: "c", applied: true } },
    { turn_id: "t3", status: "completed", text: "Nota 2", question: "otra", confirmation: { operation_id: "op2", revision: 1, contact_id: "c", cancelled: true } },
  ]);
  assert.deepEqual(messages.map((m) => m.role), ["user", "assistant", "user", "assistant", "user", "assistant"]);
  assert.equal(messages[0].text, "Pregunta");
  assert.equal(messages[1].evidence.length, 1);
  assert.equal(messages[3].confirm?.status, "succeeded");
  assert.equal(messages[5].confirm, null);
});

test("stop keeps the text so far, marks it stopped and offers a retry", () => {
  const t = run([{ type: "send", id: "a", text: "q" }, ev({ type: "content", delta: "Marina" }), { type: "stopped" }]);
  assert.equal(last(t).phase, "done");
  assert.equal(last(t).stopped, true);
  assert.equal(last(t).text, "Marina");
  assert.equal(isBusy(t), false);
});

test("playbook citation tokens are hidden while streaming too", () => {
  assert.equal(displayText("Regla [pb-e-price] y sigue"), "Regla y sigue");
  assert.equal(displayText("Regla [pb-e-pri"), "Regla");
});

test("call targets ride on the final event, are cleaned, and come back on a reload", () => {
  const targets = [
    { contact_id: "c1", contact_name: "Lucía", reason: "today_reason_due", crm_url: "https://app.hubspot.com/x" },
    { contact_id: "", reason: "nothing" },
    { contact_id: "c2", reason: "today_reason_cold", crm_url: "javascript:alert(1)" },
  ];
  const t = run([
    { type: "send", id: "a", text: "¿a quién llamo hoy?" },
    ev({ type: "final", text: "Llama a Lucía.", evidence: [], call_targets: targets }),
    ev({ type: "done", turn_id: "t1", status: "completed" }),
  ]);
  assert.deepEqual(last(t).callTargets.map((x) => [x.contact_id, x.crm_url]), [["c1", "https://app.hubspot.com/x"], ["c2", null]]);
  const restored = messagesFromTurns([{ turn_id: "t1", status: "completed", text: "Llama a Lucía.", question: "¿a quién llamo hoy?", call_targets: targets }]);
  assert.equal(restored[1].callTargets.length, 2);
});
