import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { askStepLabel, askStepsFrom, askStepsSummary } from "./ask-steps.ts";

describe("ask steps", () => {
  it("keeps only well-formed steps and normalizes state", () => {
    assert.deepEqual(
      askStepsFrom([{ tool: "get_contact", state: "done" }, { nope: 1 }, { tool: "list_notes", state: "weird", detail: 3 }, null]),
      [
        { tool: "get_contact", state: "done", detail: "" },
        { tool: "list_notes", state: "running", detail: "" },
      ],
    );
    assert.deepEqual(askStepsFrom(undefined), []);
  });

  it("labels a step with what it looked for, and falls back for an unknown tool", () => {
    const labels = { search_contacts: "Buscando contactos" };
    assert.equal(askStepLabel({ tool: "search_contacts", state: "running", detail: "Marc" }, labels, "Consultando"), "Buscando contactos · Marc");
    assert.equal(askStepLabel({ tool: "new_tool", state: "done" }, labels, "Consultando"), "Consultando");
  });

  it("summarizes finished steps", () => {
    assert.equal(askStepsSummary([], "{count} pasos", "1 paso"), null);
    assert.equal(askStepsSummary([{ tool: "a", state: "done" }], "{count} pasos", "1 paso"), "1 paso");
    assert.equal(askStepsSummary([{ tool: "a", state: "done" }, { tool: "b", state: "done" }], "{count} pasos", "1 paso"), "2 pasos");
  });
});
