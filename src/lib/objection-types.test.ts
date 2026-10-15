import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { copyAnswerTo, draftBodyWithObjections, joinNames, objectionsAfter, setInType, typesWithObjection, typesWithPlaybook, type ObjectionLibrary } from "./objection-types.ts";
import { draftPayload, criteriaFromSnapshot, stepsFromSnapshot, type EditorObjection, type EditorSnapshot } from "./playbook-editor.ts";

const price: EditorObjection = { category: "price", guidance: "Habla de valor", trigger: "Es caro" };
const email: EditorObjection = { category: "custom", id: "send-email", label: "Mándame un email", guidance: "Pide cinco minutos", trigger: "Mándame un email" };
const timing: EditorObjection = { category: "timing", guidance: "Fija una fecha" };

function library(): ObjectionLibrary {
  return {
    discovery: [price, email],
    closing: [{ ...price, guidance: "Compara con el coste de no hacerlo" }, timing],
    inbound: [],
  };
}

describe("typesWithObjection", () => {
  it("lists the types that hold the objection, in library order", () => {
    assert.deepEqual(typesWithObjection(library(), "price"), ["discovery", "closing"]);
  });

  it("tells custom objections apart by id", () => {
    const lib = { a: [{ category: "custom" as const, id: "x", guidance: "" }], b: [{ category: "custom" as const, id: "y", guidance: "" }] };
    assert.deepEqual(typesWithObjection(lib, "custom:x"), ["a"]);
    assert.deepEqual(typesWithObjection(lib, "custom:y"), ["b"]);
  });

  it("returns nothing for an unknown key or an empty library", () => {
    assert.deepEqual(typesWithObjection(library(), "trust"), []);
    assert.deepEqual(typesWithObjection({}, "price"), []);
  });
});

describe("setInType", () => {
  it("adds a copy taken from the source type when absent", () => {
    const lib = library();
    const next = setInType(lib, "custom:send-email", "inbound", true, "discovery");
    assert.deepEqual(next.inbound, [email]);
    assert.notEqual(next.inbound[0], email);
    assert.deepEqual(next.discovery, lib.discovery);
  });

  it("does not duplicate nor overwrite when the type already has it", () => {
    const lib = library();
    const next = setInType(lib, "price", "closing", true, "discovery");
    assert.equal(next, lib);
    assert.equal(next.closing[0].guidance, "Compara con el coste de no hacerlo");
  });

  it("removes the objection from the type", () => {
    const next = setInType(library(), "price", "closing", false, "discovery");
    assert.deepEqual(next.closing, [timing]);
    assert.deepEqual(next.discovery, [price, email]);
  });

  it("removing from a type that does not have it changes nothing", () => {
    const lib = library();
    assert.equal(setInType(lib, "price", "inbound", false, "discovery"), lib);
  });

  it("leaves the library unchanged when the type is the source", () => {
    const lib = library();
    assert.equal(setInType(lib, "price", "discovery", false, "discovery"), lib);
    assert.equal(setInType(lib, "price", "discovery", true, "discovery"), lib);
  });

  it("never mutates the library", () => {
    const lib = library();
    const snapshot = JSON.parse(JSON.stringify(lib));
    setInType(lib, "custom:send-email", "inbound", true, "discovery");
    setInType(lib, "price", "closing", false, "discovery");
    assert.deepEqual(lib, snapshot);
  });

  it("does nothing when the source type does not hold the objection", () => {
    const lib = library();
    assert.equal(setInType(lib, "trust", "inbound", true, "discovery"), lib);
    assert.deepEqual(setInType({}, "price", "a", true, "b"), {});
  });
});

describe("copyAnswerTo", () => {
  it("sets the guidance of every target that has the objection", () => {
    const lib = library();
    lib.inbound = [{ ...price, guidance: "otra" }];
    const next = copyAnswerTo(lib, "price", "discovery", ["closing", "inbound"]);
    assert.equal(next.closing[0].guidance, "Habla de valor");
    assert.equal(next.inbound[0].guidance, "Habla de valor");
    assert.equal(next.closing[1], timing);
    assert.equal(next.closing[0].trigger, "Es caro");
  });

  it("leaves targets without the objection and the source untouched", () => {
    const lib = library();
    const next = copyAnswerTo(lib, "custom:send-email", "discovery", ["closing", "inbound", "discovery", "missing"]);
    assert.deepEqual(next, lib);
    assert.deepEqual(Object.keys(next), Object.keys(lib));
  });

  it("never mutates the library", () => {
    const lib = library();
    const snapshot = JSON.parse(JSON.stringify(lib));
    copyAnswerTo(lib, "price", "discovery", ["closing"]);
    assert.deepEqual(lib, snapshot);
  });

  it("copies a custom answer by its id", () => {
    const lib = { a: [email], b: [{ ...email, guidance: "viejo" }, { category: "custom" as const, id: "other", guidance: "x" }] };
    const next = copyAnswerTo(lib, "custom:send-email", "a", ["b"]);
    assert.equal(next.b[0].guidance, "Pide cinco minutos");
    assert.equal(next.b[1].guidance, "x");
  });

  it("handles an empty library and a missing source", () => {
    assert.deepEqual(copyAnswerTo({}, "price", "a", ["b"]), {});
    const lib = library();
    assert.equal(copyAnswerTo(lib, "trust", "discovery", ["closing"]), lib);
  });
});

describe("objectionsAfter", () => {
  it("returns the target list with a copy of the source objection when adding", () => {
    const lib = library();
    assert.deepEqual(objectionsAfter(lib, "custom:send-email", "discovery", "closing", { kind: "set", on: true }), [...lib.closing, email]);
  });

  it("returns the target list without the objection when removing", () => {
    assert.deepEqual(objectionsAfter(library(), "price", "discovery", "closing", { kind: "set", on: false }), [timing]);
  });

  it("returns null when the target already is as asked", () => {
    assert.equal(objectionsAfter(library(), "price", "discovery", "closing", { kind: "set", on: true }), null);
    assert.equal(objectionsAfter(library(), "price", "discovery", "inbound", { kind: "set", on: false }), null);
  });

  it("copies the source answer onto the target's own objection", () => {
    const next = objectionsAfter(library(), "price", "discovery", "closing", { kind: "copy" });
    assert.deepEqual(next, [price, timing]);
  });

  it("returns null when the answers already match, or the target lacks the objection", () => {
    const lib = { ...library(), closing: [price, timing] };
    assert.equal(objectionsAfter(lib, "price", "discovery", "closing", { kind: "copy" }), null);
    assert.equal(objectionsAfter(library(), "price", "discovery", "inbound", { kind: "copy" }), null);
  });

  it("leaves the library untouched", () => {
    const lib = library();
    const before = JSON.stringify(lib);
    objectionsAfter(lib, "price", "discovery", "closing", { kind: "copy" });
    assert.equal(JSON.stringify(lib), before);
  });
});

describe("typesWithPlaybook", () => {
  it("keeps drafts, published and paused types; drops missing and importing", () => {
    const motions = { discovery: "published", closing: "draft", inbound: "missing", demo: "importing", renewal: "paused" };
    assert.deepEqual(typesWithPlaybook(motions), ["discovery", "closing", "renewal"]);
  });

  it("lists qualification only once published", () => {
    assert.deepEqual(typesWithPlaybook({ qualification: "draft", discovery: "draft" }), ["discovery"]);
    assert.deepEqual(typesWithPlaybook({ qualification: "published", discovery: "draft" }), ["qualification", "discovery"]);
  });
});

describe("joinNames", () => {
  it("joins one, two and three names", () => {
    assert.equal(joinNames(["A"], "y"), "A");
    assert.equal(joinNames(["A", "B"], "y"), "A y B");
    assert.equal(joinNames(["A", "B", "C"], "and"), "A, B and C");
    assert.equal(joinNames([], "y"), "");
  });
});

describe("draftBodyWithObjections", () => {
  const doc: EditorSnapshot & { updated_at: string; source_doc: { id: string } } = {
    source: "published",
    version_id: "v1",
    updated_at: "2026-10-15T10:00:00Z",
    source_doc: { id: "doc-7" },
    steps: [
      { step_id: "opening", label: "Apertura", criterion: "Se presenta", example: "Hola, soy Ana" },
      { step_id: "close", label: "Cierre", criterion: "Propone fecha" },
    ],
    objections: [{ category: "timing", guidance: "Fija una fecha" }],
    qualification: [{ criterion_id: "budget", label: "Presupuesto", good: "Dice una cifra" }],
  };

  it("keeps the type's own steps and qualification and only swaps the objections", () => {
    const body = draftBodyWithObjections(doc, [timing, price]);
    assert.ok(body);
    const expected = draftPayload(stepsFromSnapshot(doc), [timing, price], criteriaFromSnapshot(doc));
    assert.deepEqual(body.steps, expected.steps);
    assert.deepEqual(body.qualification, expected.qualification);
    assert.deepEqual(body.steps.map((step) => step.step_id), ["opening", "close"]);
    assert.deepEqual(body.qualification, [{ criterion_id: "budget", label: "Presupuesto", good: "Dice una cifra" }]);
    assert.deepEqual(body.objections, [
      { category: "timing", guidance: "Fija una fecha" },
      { category: "price", guidance: "Habla de valor", trigger: "Es caro" },
    ]);
  });

  it("carries the type's own revision and source for the conflict check", () => {
    const body = draftBodyWithObjections(doc, [timing]);
    assert.equal(body?.base_updated_at, "2026-10-15T10:00:00Z");
    assert.equal(body?.source_id, "doc-7");
    const bare = draftBodyWithObjections({ ...doc, updated_at: undefined, source_doc: undefined }, [timing]);
    assert.equal(bare?.base_updated_at, null);
    assert.equal(bare?.source_id, null);
  });

  it("sends a custom objection with its id and name", () => {
    const body = draftBodyWithObjections(doc, [email]);
    assert.deepEqual(body?.objections, [
      { category: "custom", id: "send-email", label: "Mándame un email", guidance: "Pide cinco minutos", trigger: "Mándame un email" },
    ]);
  });

  it("returns null when the type has no steps or the answer is too long", () => {
    assert.equal(draftBodyWithObjections({ ...doc, steps: [] }, [timing]), null);
    assert.equal(draftBodyWithObjections(doc, [{ category: "price", guidance: "x".repeat(601) }]), null);
  });
});
