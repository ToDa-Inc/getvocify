import assert from "node:assert/strict";
import test from "node:test";
import { currentStep, distinctSteps, nextShown, visibleSteps } from "./ask-activity.ts";
import type { AskStep } from "./ask-thread.ts";

const step = (id: string, status: AskStep["status"]): AskStep => ({ id, tool: "hubspot_query", status });

test("a failed step that was retried is not shown; a final failure is", () => {
  const steps = [step("1", "ok"), step("2", "failed"), step("3", "failed"), step("4", "ok")];
  assert.deepEqual(visibleSteps(steps).map((s) => s.id), ["1", "4"]);
  assert.deepEqual(visibleSteps([step("1", "ok"), step("2", "failed")]).map((s) => s.id), ["1", "2"]);
  assert.deepEqual(visibleSteps([]), []);
});

test("text glides: a trickle types steadily and a burst is caught up quickly, never overshooting", () => {
  assert.equal(nextShown(0, 4, 16), 1);
  assert.equal(nextShown(10, 10, 16), 10);
  assert.ok(nextShown(0, 40, 16) < 40, "one frame does not dump a paragraph");
  let shown = 0;
  let frames = 0;
  while (shown < 600 && frames < 200) {
    shown = nextShown(shown, 600, 16);
    frames++;
  }
  assert.equal(shown, 600);
  assert.ok(frames * 16 < 1500, "a 600-character burst settles within about a second");
  assert.equal(nextShown(5, 6, 5000), 6);
  assert.equal(nextShown(3, 9, -10), 4);
});

const run = (id: string, tool: string, status: AskStep["status"]): AskStep => ({ id, tool, status });

test("while it works, one step shows: the latest running one, else the last", () => {
  assert.equal(currentStep([]), null);
  assert.equal(currentStep([run("1", "a", "ok"), run("2", "b", "running"), run("3", "c", "ok")])?.id, "2");
  assert.equal(currentStep([run("1", "a", "running"), run("2", "b", "running")])?.id, "2");
  assert.equal(currentStep([run("1", "a", "ok"), run("2", "b", "failed")])?.id, "2");
});

test("once answered, each kind of work shows once, in first-seen order, with its latest status", () => {
  const label = (step: AskStep) => (step.tool.startsWith("x_") ? "Working" : step.tool);
  const steps = [
    run("1", "hubspot_query", "ok"),
    run("2", "hubspot_fields", "ok"),
    run("3", "hubspot_query", "ok"),
    run("4", "x_one", "ok"),
    run("5", "x_two", "ok"),
    run("6", "find_contact", "ok"),
    run("7", "find_contact", "failed"),
  ];
  const out = distinctSteps(steps, label);
  assert.deepEqual(out.map((step) => step.tool), ["hubspot_query", "hubspot_fields", "x_two", "find_contact"]);
  assert.deepEqual(out.map((step) => step.id), ["1", "2", "4", "6"]);
  assert.equal(out[3].status, "failed");
  assert.deepEqual(distinctSteps([], label), []);
});
