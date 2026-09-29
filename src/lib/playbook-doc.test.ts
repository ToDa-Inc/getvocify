import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  addableTypes,
  appendDictation,
  editorFromStructure,
  hiddenObjectionCategories,
  needsCriterion,
  percent,
  playbookRows,
  publishBlocker,
  ruleSummary,
  sourceKindForFile,
  stepRate,
  typeKeyFromName,
  validationToShow,
  visibleObjections,
  weakestStep,
  type CatalogType,
  type RuleCopy,
} from "./playbook-doc.ts";

const step = (label: string, criterion = "", key = label || "k") => ({ key, label, criterion });

describe("playbook document", () => {
  it("reads PDFs, audio and text files, and nothing else", () => {
    assert.equal(sourceKindForFile({ name: "guion.PDF", type: "" }), "pdf");
    assert.equal(sourceKindForFile({ name: "nota.m4a", type: "" }), "audio");
    assert.equal(sourceKindForFile({ name: "x", type: "audio/webm" }), "audio");
    assert.equal(sourceKindForFile({ name: "proceso.txt", type: "text/plain" }), "text");
    assert.equal(sourceKindForFile({ name: "deck.pptx", type: "application/vnd.ms-powerpoint" }), null);
  });

  it("adds dictation after what is written, never replacing it", () => {
    assert.equal(appendDictation("", " hola "), "hola");
    assert.equal(appendDictation("Primero llamamos.\n", "Luego cualificamos."), "Primero llamamos.\n\nLuego cualificamos.");
    assert.equal(appendDictation("algo", "   "), "algo");
  });

  it("never shows an error on a step nobody has touched", () => {
    assert.equal(validationToShow(step(""), false), null);
    assert.equal(validationToShow(step(""), true), null);
    assert.equal(validationToShow(step(""), false, true), "empty_label");
    assert.equal(validationToShow(step("x".repeat(90)), true), "label_too_long");
    assert.equal(validationToShow(step("Apertura"), true), null);
  });

  it("points Publish at the step to fix", () => {
    assert.deepEqual(publishBlocker([], []), { code: "no_steps", stepIndex: null });
    assert.deepEqual(publishBlocker([step("Apertura"), step("")], []), { code: "empty_label", stepIndex: 1 });
    assert.equal(publishBlocker([step("Apertura", "Se presenta")], []), null);
  });

  it("shows answered objections and the ones the team hears, most frequent first", () => {
    const rows = visibleObjections(
      [{ category: "price", guidance: "¿Comparado con qué?" }],
      [
        { category: "timing", count: 9, share: 0.18, answered: false, best_example: "Lo vemos en enero" },
        { category: "price", count: 4, share: 0.08, answered: true, best_example: null },
        { category: "trust", count: 0, share: 0, answered: false, best_example: null },
      ],
      ["authority"],
    );
    assert.deepEqual(rows.map((row) => row.category), ["timing", "price", "authority"]);
    assert.equal(rows[0].bestExample, "Lo vemos en enero");
    assert.deepEqual(hiddenObjectionCategories(rows), ["competitor", "status_quo", "trust", "other"]);
  });

  it("keeps a category on screen while its answer is being cleared", () => {
    const rows = visibleObjections([{ category: "trust", guidance: "" }], null);
    assert.deepEqual(rows.map((row) => row.category), ["trust"]);
  });

  it("gives a step rate only when there is one, and names the weakest step", () => {
    const insights = {
      period: "week",
      calls: 40,
      steps: [
        { step_id: "opening", met: 30, missed: 10, rate: 0.75 },
        { step_id: "pain", met: 8, missed: 22, rate: 0.2667 },
        { step_id: "meeting", met: 2, missed: 3, rate: null },
      ],
      objections: [],
    };
    assert.equal(stepRate(insights, "opening"), 75);
    assert.equal(stepRate(insights, "meeting"), null);
    assert.equal(stepRate(null, "opening"), null);
    assert.equal(weakestStep(insights), "pain");
    assert.equal(weakestStep({ ...insights, steps: insights.steps.slice(0, 1) }), null);
    assert.equal(percent(0.184), "18 %");
  });

  it("turns a structure result into editor rows, dropping unknown categories", () => {
    let n = 0;
    const { steps, objections } = editorFromStructure(
      {
        steps: [{ label: "Apertura", criterion: "Se presenta", step_id: "apertura" }],
        objections: [
          { category: "price", guidance: "¿Comparado con qué?" },
          { category: "weather", guidance: "x" },
          { category: "timing", guidance: "  " },
        ],
      },
      () => `k${++n}`,
    );
    assert.equal(steps[0].key, "k1");
    assert.equal(steps[0].example, "");
    assert.deepEqual(objections, [{ category: "price", guidance: "¿Comparado con qué?" }]);
  });

  it("flags a step whose criterion only repeats its name", () => {
    assert.equal(needsCriterion(step("Apertura", "Apertura")), true);
    assert.equal(needsCriterion(step("Apertura", "")), true);
    assert.equal(needsCriterion(step("Apertura", "Pide 30 segundos")), false);
  });

  it("orders rows by catalog, hides unpublished qualification and flags unrouted types", () => {
    const motions = { sales: "draft", closing: "missing", discovery: "published", qualification: "missing" } as const;
    const off = playbookRows({ ...motions }, null, false);
    assert.deepEqual(off.map((row) => row.key), ["discovery", "closing", "sales"]);
    assert.deepEqual(off.map((row) => row.unrouted), [false, false, true]);
    assert.equal(off[0].role, "sdr");

    const rule = { role: "sdr" as const, channels: ["call" as const], contact: "contacted" as const, deal_stages: [] };
    const on = playbookRows({ ...motions }, { sales: { label: "Rellamada", role: "sdr", applies_to: rule, goal: null, catalog: false } }, true);
    assert.equal(on.find((row) => row.key === "sales")?.unrouted, false);
    const noRule = playbookRows({ ...motions }, { sales: { label: null, role: null, applies_to: null, goal: null, catalog: false } }, true);
    assert.equal(noRule.find((row) => row.key === "sales")?.unrouted, true);
  });

  it("summarises a rule in one line", () => {
    const copy: RuleCopy = {
      roles: { sdr: "SDR", ae: "AE", any: "todos" },
      channels: { call: "Llamadas", meeting: "Reuniones", visit: "Visitas" },
      contacts: { new: "contacto nuevo", contacted: "ya contactado", inbound: "lead inbound", any: "cualquiera" },
      stages: "{count} etapas del CRM",
      join: " y ",
    };
    assert.equal(
      ruleSummary({ role: "sdr", channels: ["call"], contact: "new", deal_stages: [] }, copy),
      "Llamadas · SDR · contacto nuevo",
    );
    assert.equal(
      ruleSummary({ role: "any", channels: ["meeting", "visit"], contact: "any", deal_stages: ["a", "b"] }, copy),
      "Reuniones y Visitas · 2 etapas del CRM",
    );
    assert.equal(ruleSummary(null, copy), null);
  });

  it("offers only catalog types the company doesn't have, and slugs custom names", () => {
    const type = (key: string) => ({ key }) as unknown as CatalogType;
    assert.deepEqual(addableTypes([type("discovery"), type("inbound")], { discovery: "published" }).map((t) => t.key), ["inbound"]);
    assert.equal(typeKeyFromName("Rellamada de cualificación"), "rellamada_de_cualificacion");
  });
});
