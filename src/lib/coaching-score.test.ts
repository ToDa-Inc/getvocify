import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { coachingSurface } from "./coaching-score.ts";

describe("coaching surface", () => {
  it("shows the stored mark and does not rebuild it from the steps", () => {
    const surface = coachingSurface({
      status: "ready",
      value: 6,
      reason: null,
      adherence: 0.5,
      coverage: 2 / 3,
      strengths: ["Nombró el precio"],
      improvements: ["No cerró el siguiente paso"],
      crm_outcome: "closed_won",
      met_steps: 0,
    }, "member");
    assert.equal(surface.kind, "scored");
    if (surface.kind === "scored") {
      assert.equal(surface.value, 6);
      assert.equal(surface.adherence, 0.5);
      assert.equal(surface.crmOutcome, "closed_won");
      assert.equal(surface.strengths[0], "Nombró el precio");
    }
  });

  it("does not show a zero when the score is empty", () => {
    const partial = coachingSurface({
      status: "partial",
      value: null,
      reason: "insufficient_evidence",
      adherence: null,
      coverage: 0,
      strengths: ["Preguntó por el decisor"],
      improvements: [],
    }, "member");
    assert.equal(partial.kind, "unscored");
    if (partial.kind === "unscored") {
      assert.equal(partial.title, "Sin puntuación");
      assert.equal(partial.strengths[0], "Preguntó por el decisor");
    }
    const setup = coachingSurface({
      status: "unavailable",
      value: null,
      reason: "missing_playbook",
      adherence: null,
      coverage: null,
    }, "member");
    assert.equal(setup.kind, "setup");
    if (setup.kind === "setup") assert.equal(setup.action, null);
  });
});
