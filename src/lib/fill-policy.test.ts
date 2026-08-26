import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { classifyFillPolicy, FILL_POLICY_LABELS } from "./fill-policy.ts";

describe("classifyFillPolicy", () => {
  it("matches backend identity / strategy / research / call note / explicit", () => {
    assert.equal(classifyFillPolicy({ name: "firstname", label: "First name" }), "identity");
    assert.equal(classifyFillPolicy({ name: "call_angle", label: "Call angle", description: "pre-call talk track" }), "strategy");
    assert.equal(classifyFillPolicy({ name: "sales_motion", label: "Sales motion", description: "ICP fit" }), "research");
    assert.equal(classifyFillPolicy({ name: "description" }), "call_note");
    assert.equal(classifyFillPolicy({ name: "amount", label: "Amount" }), "explicit");
    assert.equal(classifyFillPolicy({ name: "vocify_context_status", label: "Vocify Context Status" }), "strategy");
  });

  it("prefers server-provided fill_policy", () => {
    assert.equal(classifyFillPolicy({ name: "amount", fill_policy: "identity" }), "identity");
    assert.equal(FILL_POLICY_LABELS.strategy, "Never from calls");
  });
});
