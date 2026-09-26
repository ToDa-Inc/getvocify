import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { askCallTargets, dialerAvailable } from "./ask-calls.ts";

const lucia = {
  contact_id: "p-2",
  connection_id: "crm-A",
  provider: "hubspot",
  contact_name: "Lucía Pérez",
  reason: "pain_agree_next_step",
  next_action: "agree_next_step",
  crm_url: "https://app.hubspot.com/contacts/1/record/0-1/p-2",
};

describe("ask call targets", () => {
  it("has none when the turn omits the key", () => {
    assert.deepEqual(askCallTargets({}), []);
    assert.deepEqual(askCallTargets({ call_targets: null }), []);
  });

  it("keeps the order and caps at five", () => {
    const rows = Array.from({ length: 7 }, (_, n) => ({ ...lucia, contact_id: `p-${n}` }));
    assert.deepEqual(askCallTargets({ call_targets: rows }).map((row) => row.contact_id), ["p-0", "p-1", "p-2", "p-3", "p-4"]);
  });

  it("drops a row without contact or reason", () => {
    const rows = [{ ...lucia, contact_id: "" }, { ...lucia, reason: "" }, lucia];
    assert.deepEqual(askCallTargets({ call_targets: rows }).map((row) => row.contact_id), ["p-2"]);
  });

  it("keeps only https CRM links", () => {
    const [row] = askCallTargets({ call_targets: [{ ...lucia, crm_url: "javascript:alert(1)" }] });
    assert.equal(row.crm_url, null);
    assert.equal(askCallTargets({ call_targets: [lucia] })[0].crm_url, lucia.crm_url);
  });
});

describe("dialer availability", () => {
  it("is available on the web dashboard of a company that can dial", () => {
    assert.equal(dialerAvailable({ desktop: false, company: { canUseDialer: true } }), true);
  });

  it("is not available on desktop, behind the paywall or without the dialer plan", () => {
    assert.equal(dialerAvailable({ desktop: true, company: { canUseDialer: true } }), false);
    assert.equal(dialerAvailable({ desktop: false, company: { paywalled: true, canUseDialer: true } }), false);
    assert.equal(dialerAvailable({ desktop: false, company: { canUseDialer: false } }), false);
  });
});
