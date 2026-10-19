import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { canSave, mergeScope, rowProblem, scopeProblem, moveItem, removedWithContent, requestFor, suggestedProcess, toRequest, typesSummary, type DraftType, type SavedType } from "./sales-process.ts";

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

  it("needs an objective for every interaction of the funnel, but not for the other calls, and never a description", () => {
    assert.equal(canSave([t("Demo", { goal: "" })]), false);
    assert.equal(canSave([t("Demo", { recognize: "  " })]), true);
    assert.equal(canSave([t("Demo"), { label: "SAC", stage: "other" }]), true);
  });

  it("says what each row is missing and checks only the part the window saves", () => {
    const legacy = t("Cold call", { goal: undefined });
    const sac: DraftType = { label: "SAC", stage: "other" };
    assert.equal(rowProblem(t("  "), [t("  ")]), "empty_name");
    assert.equal(rowProblem(t("Demo", { goal: " " }), []), "goal_required");
    assert.equal(rowProblem(sac, [t("sac"), sac]), "duplicate_name");
    assert.equal(rowProblem(sac, [legacy, sac]), null);
    // A funnel saved without goals does not stop the calls outside it, but the funnel window asks for them.
    assert.equal(scopeProblem([sac], [legacy, sac]), null);
    assert.equal(scopeProblem([legacy], [legacy, sac]), "goal_required");
    assert.equal(scopeProblem([], []), "empty_name");
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

describe("what a window saves", () => {
  const saved: SavedType[] = [
    { key: "cold", label: "Llamada en frío", stage: "first_contact", goal: "Reunión", recognize: "Primer contacto", step_count: 6 },
    { key: "demo", label: "Demo", stage: "deal", goal: "Cerrar", step_count: 4 },
  ];

  it("the calls outside the funnel never take the funnel with them, even from an empty draft", () => {
    const body = requestFor(saved, "other", [{ label: "SAC", stage: "other" }]);
    assert.equal(body.scope, "other");
    assert.deepEqual(body.types.map((x) => x.key ?? x.label), ["cold", "demo", "SAC"]);
    assert.deepEqual(body.types[0], { key: "cold", label: "Llamada en frío", stage: "first_contact", goal: "Reunión", recognize: "Primer contacto" });
  });

  it("the funnel window sends its own list first and the other calls as they are saved", () => {
    const withOther: SavedType[] = [...saved, { key: "sac", label: "SAC", stage: "other" }];
    const body = requestFor(withOther, "funnel", [{ key: "demo", label: "Demo", stage: "deal", goal: "Cerrar" }]);
    assert.deepEqual(body.types.map((x) => x.key), ["demo", "sac"]);
  });
});
