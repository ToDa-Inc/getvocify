import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import { SALES_ROLE_OPTIONS, salesRoleLabel } from "./sales-role.ts";

describe("SALES_ROLE_OPTIONS", () => {
  it("lists sdr, ae, general in that order", () => {
    assert.deepEqual(SALES_ROLE_OPTIONS, ["sdr", "ae", "general"]);
  });
});

describe("salesRoleLabel", () => {
  it("maps known roles in English and Spanish", () => {
    assert.equal(salesRoleLabel("sdr", productCatalog.EN), "SDR");
    assert.equal(salesRoleLabel("ae", productCatalog.EN), "AE");
    assert.equal(salesRoleLabel("general", productCatalog.EN), "Both");
    assert.equal(salesRoleLabel("sdr", productCatalog.ES), "SDR");
    assert.equal(salesRoleLabel("ae", productCatalog.ES), "AE");
    assert.equal(salesRoleLabel("general", productCatalog.ES), "Ambos");
  });

  it("falls back to general for unknown values", () => {
    assert.equal(salesRoleLabel("unknown", productCatalog.EN), "Both");
    assert.equal(salesRoleLabel("", productCatalog.ES), "Ambos");
    assert.equal(salesRoleLabel(null, productCatalog.EN), "Both");
    assert.equal(salesRoleLabel(undefined, productCatalog.ES), "Ambos");
  });
});
