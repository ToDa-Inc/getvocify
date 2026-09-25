import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { memoMeetingChecklistView } from "./memo-meeting-checklist.ts";

describe("memoMeetingChecklistView", () => {
  it("hides when applicable is zero", () => {
    assert.equal(
      memoMeetingChecklistView(
        { applicable: 0, observed: 0, steps: [{ label: "Intro", status: "pending" }] },
        { progressTemplate: "{met} of {applicable}", doneLabel: "Done" },
      ),
      null,
    );
  });

  it("shows both step labels when two steps apply", () => {
    const view = memoMeetingChecklistView(
      {
        applicable: 2,
        observed: 1,
        steps: [
          { label: "Saludo", status: "met" },
          { label: "Precio", status: "pending" },
        ],
      },
      { progressTemplate: "{met} of {applicable}", doneLabel: "Done" },
    );
    assert.ok(view);
    assert.equal(view!.progress, "1 of 2");
    assert.equal(view!.steps.length, 2);
    assert.equal(view!.steps[0].label, "Saludo");
    assert.equal(view!.steps[1].label, "Precio");
  });

  it("includes the done label on met steps", () => {
    const view = memoMeetingChecklistView(
      {
        applicable: 1,
        observed: 1,
        steps: [{ label: "Cierre", status: "met" }],
      },
      { progressTemplate: "{met} de {applicable}", doneLabel: "Hecho" },
    );
    assert.ok(view);
    assert.equal(view!.steps[0].kind, "met");
    assert.equal(view!.steps[0].doneLabel, "Hecho");
  });
});
