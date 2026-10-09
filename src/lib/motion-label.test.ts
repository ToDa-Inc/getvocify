import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import { motionLabel } from "./motion-label.ts";

describe("motionLabel", () => {
  it("maps known motion keys in English and Spanish", () => {
    assert.equal(motionLabel("discovery", productCatalog.EN.motions), "Discovery");
    assert.equal(motionLabel("qualification", productCatalog.EN.motions), "Qualification");
    assert.equal(motionLabel("closing", productCatalog.EN.motions), "Closing");
    assert.equal(motionLabel("discovery", productCatalog.ES.motions), "Descubrimiento");
    assert.equal(motionLabel("qualification", productCatalog.ES.motions), "Calificación");
    assert.equal(motionLabel("closing", productCatalog.ES.motions), "Cierre");
  });

  it("returns unknown keys unchanged", () => {
    assert.equal(motionLabel("enterprise", productCatalog.ES.motions), "enterprise");
  });
});
