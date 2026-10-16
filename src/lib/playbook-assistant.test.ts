import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  intakeSummary,
  progressText,
  rateLabel,
  savedLine,
  splitQuestion,
  topicLabel,
  trialMeter,
  viewFromParams,
  type IntakeLike,
} from "./playbook-assistant.ts";

const editor = (steps: number, objections: string[]) => ({
  steps: Array.from({ length: steps }, () => ({})),
  objections: objections.map((category) => ({ category })),
});

describe("playbook assistant helpers", () => {
  it("reads the open view from the URL and ignores anything else", () => {
    assert.equal(viewFromParams(new URLSearchParams("view=trial")), "trial");
    assert.equal(viewFromParams(new URLSearchParams("view=assistant&x=1")), "assistant");
    assert.equal(viewFromParams(new URLSearchParams("view=improve")), "improve");
    assert.equal(viewFromParams(new URLSearchParams("view=xyz")), null);
    assert.equal(viewFromParams(new URLSearchParams("")), null);
  });

  it("shows a percentage only from three cases on, and the plain count below", () => {
    assert.deepEqual(rateLabel(3, 4), { kind: "rate", text: "75%" });
    assert.deepEqual(rateLabel(3, 3), { kind: "rate", text: "100%" });
    assert.deepEqual(rateLabel(2, 2), { kind: "count", text: "2 de 2" });
    assert.deepEqual(rateLabel(0, 0), { kind: "count", text: "0 de 0" });
    assert.deepEqual(rateLabel(1, 2, { of: "of" }), { kind: "count", text: "1 of 2" });
    assert.deepEqual(rateLabel(1, 5, { min: 6 }), { kind: "count", text: "1 de 5" });
  });

  it("counts what a document gave without repeating call types", () => {
    const a: IntakeLike = {
      fallback: false,
      types: [{ sales_motion_key: "discovery", editor: editor(3, ["price", "custom", "custom"]) }],
      company: { knowledge: { proofs: [{ customer: "Gestoría Ríos" }] } },
    };
    const b: IntakeLike = {
      fallback: false,
      types: [
        { sales_motion_key: "discovery", editor: editor(4, ["price", "timing", "custom"]) },
        { sales_motion_key: "closing", editor: editor(2, ["price"]) },
      ],
      company: null,
    };
    // The same call type seen twice counts once, with what its last version holds.
    assert.deepEqual(intakeSummary([a, b]), { types: 2, steps: 6, objections: 3, questions: 1, proofs: 1 });
  });

  it("adds nothing for a document that could not be read", () => {
    const failed: IntakeLike = { fallback: true, types: [], company: null };
    assert.deepEqual(intakeSummary([failed]), { types: 0, steps: 0, objections: 0, questions: 0, proofs: 0 });
    assert.deepEqual(intakeSummary([]), { types: 0, steps: 0, objections: 0, questions: 0, proofs: 0 });
  });

  it("says what was saved in one short line", () => {
    assert.equal(savedLine("Integración con Salesforce", "Sí, con Salesforce y HubSpot."), "Integración con Salesforce: Sí, con Salesforce y HubSpot.");
    const long = savedLine("Precio", "x".repeat(300));
    assert.equal(long.length, 90);
    assert.ok(long.endsWith("…"));
    assert.equal(savedLine("", "Una respuesta."), "Una respuesta.");
  });

  it("numbers the question on screen without going past the total", () => {
    assert.equal(progressText({ answered: 0, skipped: 0, total: 10 }, "de"), "1 de 10");
    assert.equal(progressText({ answered: 3, skipped: 1, total: 10 }, "de"), "5 de 10");
    assert.equal(progressText({ answered: 10, skipped: 0, total: 10 }, "of"), "10 of 10");
  });

  it("draws one segment per case: done ones coloured by verdict, the rest pending", () => {
    assert.deepEqual(trialMeter(["approve", "corrected"], 4), ["approved", "corrected", "pending", "pending"]);
    assert.deepEqual(trialMeter(["unknown", "never_say", "branch", "approve"], 4), ["unknown", "corrected", "corrected", "approved"]);
    assert.deepEqual(trialMeter([], 0), []);
    assert.equal(trialMeter(["approve", "approve", "approve"], 2).length, 3);
  });

  it("separates the customer's words from the question so they can be shown as a quote", () => {
    assert.deepEqual(
      splitQuestion("Un cliente dijo «Y si no nos gusta, ¿cómo cancelamos?» ¿Qué respondéis?", "Y si no nos gusta, ¿cómo cancelamos?"),
      { lead: "Un cliente dijo", quote: "Y si no nos gusta, ¿cómo cancelamos?", ask: "¿Qué respondéis?" },
    );
    assert.deepEqual(
      splitQuestion("A customer asks “How much does it cost?” What do you answer?", "How much does it cost?"),
      { lead: "A customer asks", quote: "How much does it cost?", ask: "What do you answer?" },
    );
  });

  it("keeps the whole sentence when there is no quote to separate", () => {
    assert.deepEqual(splitQuestion("Tu material no coincide sobre los precios.", null), { lead: "", quote: null, ask: "Tu material no coincide sobre los precios." });
    assert.deepEqual(splitQuestion("Algo distinto", "no está"), { lead: "", quote: null, ask: "Algo distinto" });
  });

  it("names a topic by its kind or by the team's own objection", () => {
    const names = { kinds: { price: "Precio" }, question: "Preguntas del producto", none: "Lo que Vocify no reconoce", unknown: "Sin clasificar" };
    assert.equal(topicLabel("price", names), "Precio");
    assert.equal(topicLabel("question", names), "Preguntas del producto");
    assert.equal(topicLabel("none", names), "Lo que Vocify no reconoce");
    assert.equal(topicLabel("unknown", names), "Sin clasificar");
    assert.equal(topicLabel("Mándame un email", names), "Mándame un email");
    assert.equal(topicLabel("", names), "Sin clasificar");
  });
});
