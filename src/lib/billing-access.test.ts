import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  companyCanUseDialer,
  companyIsPaywalled,
  yearlyDiscountPercent,
  yearlyMonthlyAmount,
} from "./billing-access.ts";

describe("companyIsPaywalled", () => {
  it("trusts the explicit flag", () => {
    assert.equal(companyIsPaywalled({ paywalled: true, accessMode: "open" }), true);
    assert.equal(companyIsPaywalled({ paywalled: false, accessMode: "paywalled" }), false);
  });

  it("locks only paywalled unpaid companies", () => {
    assert.equal(companyIsPaywalled({ accessMode: "open", billingStatus: "none" }), false);
    assert.equal(companyIsPaywalled({ accessMode: "unlocked", billingStatus: "canceled" }), false);
    assert.equal(companyIsPaywalled({ accessMode: "paywalled", billingStatus: "none" }), true);
    assert.equal(companyIsPaywalled({ accessMode: "paywalled", billingStatus: "active" }), false);
  });
});

describe("companyCanUseDialer", () => {
  it("trusts the explicit flag", () => {
    assert.equal(companyCanUseDialer({ canUseDialer: false, planType: "pro" }), false);
    assert.equal(companyCanUseDialer({ canUseDialer: true, planType: "starter" }), true);
  });

  it("keeps the dialer on open unpaid workspaces and Pro", () => {
    assert.equal(companyCanUseDialer({ accessMode: "open", billingStatus: "none" }), true);
    assert.equal(
      companyCanUseDialer({ accessMode: "open", billingStatus: "active", planType: "starter" }),
      false,
    );
    assert.equal(
      companyCanUseDialer({ accessMode: "open", billingStatus: "active", planType: "pro" }),
      true,
    );
    assert.equal(companyCanUseDialer({ accessMode: "unlocked", billingStatus: "none" }), true);
  });
});

describe("yearly pricing", () => {
  it("marks the yearly cut as a percent and a monthly equivalent", () => {
    assert.equal(yearlyDiscountPercent(30, 300), 17);
    assert.equal(yearlyDiscountPercent(50, 500), 17);
    assert.equal(yearlyMonthlyAmount(300), 25);
    assert.equal(yearlyMonthlyAmount(500), 42);
  });
});
