import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  MAX_STEPS,
  draftError,
  draftPayload,
  isLegacyBlob,
  moveStep,
  objectionsFromSnapshot,
  parsePlaybookText,
  stepError,
  templateSteps,
} from "./playbook-editor.ts";

describe("playbook editor", () => {
  it("turns numbered lines into steps with label and description", () => {
    const steps = parsePlaybookText(
      "Nuestro proceso:\n1. Apertura: se presenta y pide 2 minutos\n2) Descubrir el dolor — pregunta cómo lo hacen hoy\n   y qué les falla\n- Cualificar",
    );
    assert.deepEqual(
      steps.map((step) => [step.label, step.criterion]),
      [
        ["Apertura", "se presenta y pide 2 minutos"],
        ["Descubrir el dolor", "pregunta cómo lo hacen hoy y qué les falla"],
        ["Cualificar", "Cualificar"],
      ],
    );
  });

  it("uses paragraphs when the text has no markers", () => {
    const steps = parsePlaybookText("Abre con el motivo de la llamada. Sé breve.\n\nPregunta por el problema actual.");
    assert.equal(steps.length, 2);
    assert.equal(steps[0].label, "Abre con el motivo de la llamada");
    assert.equal(steps[0].criterion, "Abre con el motivo de la llamada. Sé breve.");
  });

  it("never returns more than the maximum steps or empty ones", () => {
    const text = Array.from({ length: 20 }, (_, i) => `${i + 1}. Paso ${i + 1}`).join("\n");
    assert.equal(parsePlaybookText(text).length, MAX_STEPS);
    assert.deepEqual(parsePlaybookText("   \n\n "), []);
  });

  it("has templates per flow with stable step ids", () => {
    const discovery = templateSteps("discovery", "es");
    assert.equal(discovery[0].step_id, "opening");
    assert.equal(discovery[discovery.length - 1].step_id, "meeting");
    assert.equal(templateSteps("closing", "en")[0].label, "Agenda and goal");
    assert.equal(templateSteps("custom_type", "es")[0].step_id, "opening");
  });

  it("validates like the backend", () => {
    assert.equal(stepError({ key: "a", label: " ", criterion: "" }), "empty_label");
    assert.equal(stepError({ key: "a", label: "x".repeat(81), criterion: "" }), "label_too_long");
    assert.equal(stepError({ key: "a", label: "ok", criterion: "x".repeat(401) }), "criterion_too_long");
    assert.equal(draftError([], []), "no_steps");
    assert.equal(draftError([{ key: "a", label: "ok", criterion: "" }], [{ category: "price", guidance: "x".repeat(601) }]), "guidance_too_long");
    assert.equal(draftError([{ key: "a", label: "ok", criterion: "" }], []), null);
  });

  it("sends only what the backend reads and drops empty answers", () => {
    const payload = draftPayload(
      [{ key: "k", step_id: "opening", label: " Apertura ", criterion: " se  presenta ", example: " " }],
      [{ category: "price", guidance: " ROI " }, { category: "timing", guidance: "  " }],
    );
    assert.deepEqual(payload, {
      steps: [{ step_id: "opening", label: "Apertura", criterion: "se presenta" }],
      objections: [{ category: "price", guidance: "ROI" }],
    });
  });

  it("spots a legacy single-block import", () => {
    assert.equal(isLegacyBlob([{ step_id: "imported", criterion: "todo" }]), true);
    assert.equal(isLegacyBlob([{ step_id: "a", criterion: "x".repeat(500) }]), true);
    assert.equal(isLegacyBlob([{ step_id: "a", criterion: "ok" }, { step_id: "b", criterion: "ok" }]), false);
  });

  it("moves steps within bounds and keeps unknown objection categories out", () => {
    const steps = templateSteps("discovery", "es");
    assert.equal(moveStep(steps, 0, 1)[0].step_id, "reason");
    assert.equal(moveStep(steps, 0, -1), steps);
    assert.deepEqual(
      objectionsFromSnapshot({ source: "draft", version_id: null, steps: [], objections: [{ category: "process", guidance: "x" }, { category: "price", guidance: "y" }] }),
      [{ category: "price", guidance: "y" }],
    );
  });
});
