import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { typeName } from "./type-name.ts";

const labels = { discovery: "Descubrimiento", demo: "Demo" };
const motions = { closing: "Cierre" };

describe("typeName", () => {
  it("uses the app's name for a catalog type", () => {
    assert.equal(typeName("discovery", labels, { discovery: { label: "Mi discovery", catalog: true } }, motions), "Descubrimiento");
    assert.equal(typeName("discovery", labels, {}, motions), "Descubrimiento");
  });

  it("keeps the company's own name when the type is not from the catalog", () => {
    assert.equal(typeName("demo", labels, { demo: { label: "Demo técnica", catalog: false } }, motions), "Demo técnica");
    assert.equal(typeName("renewal", labels, { renewal: { label: "Renovación", catalog: false } }, motions), "Renovación");
  });

  it("falls back to the base flow name and then to the key", () => {
    assert.equal(typeName("closing", labels, {}, motions), "Cierre");
    assert.equal(typeName("x_y", labels, {}, motions), "x_y");
  });
});
