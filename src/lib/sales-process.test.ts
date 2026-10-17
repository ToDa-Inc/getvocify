import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { canSave, moveItem, removedWithContent, suggestedProcess, toRequest, typesSummary, type DraftType } from "./sales-process.ts";

const t = (label: string, over: Partial<DraftType> = {}): DraftType => ({ label, stage: "first_contact", ...over });

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

  it("sends trimmed names, keeps the keys of the types that exist and drops empty descriptions", () => {
    const body = toRequest([t(" Llamada en frío ", { key: "cold", recognize: " " }), t("Demo", { stage: "deal", recognize: "Con el decisor" })]);
    assert.deepEqual(body, {
      types: [
        { key: "cold", label: "Llamada en frío", stage: "first_contact" },
        { label: "Demo", stage: "deal", recognize: "Con el decisor" },
      ],
    });
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
