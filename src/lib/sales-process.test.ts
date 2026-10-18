import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { canSave, mergeScope, moveItem, removedWithContent, suggestedProcess, toRequest, typesSummary, type DraftType } from "./sales-process.ts";

const t = (label: string, over: Partial<DraftType> = {}): DraftType => ({ label, stage: "first_contact", goal: `Objetivo de ${label}`, recognize: `Cómo es ${label}`, ...over });

describe("sales process helpers", () => {
  it("moves a type up or down and stays put at the ends", () => {
    const list = [t("A"), t("B"), t("C")];
    assert.deepEqual(moveItem(list, 1, -1).map((x) => x.label), ["B", "A", "C"]);
    assert.deepEqual(moveItem(list, 1, 1).map((x) => x.label), ["A", "C", "B"]);
    assert.equal(moveItem(list, 0, -1), list);
    assert.equal(moveItem(list, 2, 1), list);
    assert.deepEqual(list.map((x) => x.label), ["A", "B", "C"]);
  });

  it("can be saved with at least one named type and no repeated names", () => {
    assert.equal(canSave([]), false);
    assert.equal(canSave([t("  ")]), false);
    assert.equal(canSave([t("Demo"), t("demo")]), false);
    assert.equal(canSave([t("Demo"), t("Cierre")]), true);
  });

  it("sends trimmed names, keeps the keys of the types that exist and drops empty goals and descriptions", () => {
    const body = toRequest([
      t(" Llamada en frío ", { key: "cold", goal: " Reunión ", recognize: " Primer contacto " }),
      { label: "SAC", stage: "other", goal: " ", recognize: "" },
    ]);
    assert.deepEqual(body, {
      types: [
        { key: "cold", label: "Llamada en frío", stage: "first_contact", goal: "Reunión", recognize: "Primer contacto" },
        { label: "SAC", stage: "other" },
      ],
    });
  });

  it("needs an objective and a description for every interaction of the funnel, but not for the other calls", () => {
    assert.equal(canSave([t("Demo", { goal: "" })]), false);
    assert.equal(canSave([t("Demo", { recognize: "  " })]), false);
    assert.equal(canSave([t("Demo"), { label: "SAC", stage: "other" }]), true);
  });

  it("edits one scope and leaves the other where it is: the funnel first, the other calls after", () => {
    const all = [t("A"), t("B", { stage: "deal" }), { label: "SAC", stage: "other" as const }];
    const edited = mergeScope(all, "funnel", [t("B", { stage: "deal" }), t("A")]);
    assert.deepEqual(edited.map((x) => x.label), ["B", "A", "SAC"]);
    const other = mergeScope(all, "other", [{ label: "Técnica", stage: "other" }, { label: "SAC", stage: "other" }]);
    assert.deepEqual(other.map((x) => x.label), ["A", "B", "Técnica", "SAC"]);
  });

  it("names the types that would be removed and already have something written", () => {
    const original = [
      { key: "cold", label: "Llamada en frío", stage: "first_contact" as const, step_count: 5 },
      { key: "demo", label: "Demo", stage: "deal" as const, step_count: 0 },
      { key: "close", label: "Cierre", stage: "deal" as const, step_count: 3 },
    ];
    assert.deepEqual(removedWithContent(original, [t("Llamada en frío", { key: "cold" })]), ["Cierre"]);
    assert.deepEqual(removedWithContent(original, original.map((o) => t(o.label, { key: o.key }))), []);
  });

  it("offers a starting point that is only a suggestion", () => {
    const names = ["Llamada en frío", "Discovery", "Demo", "Cierre"];
    const list = suggestedProcess(names);
    assert.deepEqual(list.map((x) => x.label), names);
    assert.deepEqual(list.map((x) => x.stage), ["first_contact", "first_contact", "deal", "deal"]);
    assert.ok(list.every((x) => x.key === undefined));
  });

  it("summarises what a person runs: all, one or two names, or how many", () => {
    const types = [{ key: "a", label: "Fría" }, { key: "b", label: "Discovery" }, { key: "c", label: "Demo" }];
    assert.equal(typesSummary(null, types, "Todas", "{count} tipos"), "Todas");
    assert.equal(typesSummary(["a", "b", "c"], types, "Todas", "{count} tipos"), "Todas");
    assert.equal(typesSummary(["b"], types, "Todas", "{count} tipos"), "Discovery");
    assert.equal(typesSummary(["a", "c"], types, "Todas", "{count} tipos"), "Fría, Demo");
    assert.equal(typesSummary(["gone"], types, "Todas", "{count} tipos"), "Todas");
    const four = [...types, { key: "d", label: "Cierre" }];
    assert.equal(typesSummary(["a", "b", "c"], four, "Todas", "{count} tipos"), "3 tipos");
  });
});
