import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { motionLabel } from "./motion-label.ts";

describe("motionLabel", () => {
  it("maps known motion keys to Spanish labels", () => {
    assert.equal(motionLabel("discovery"), "Descubrimiento");
    assert.equal(motionLabel("qualification"), "Calificación");
    assert.equal(motionLabel("closing"), "Cierre");
  });

  it("returns unknown keys unchanged", () => {
    assert.equal(motionLabel("enterprise"), "enterprise");
  });
});
