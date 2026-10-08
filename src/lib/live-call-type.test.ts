import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  NO_CALL_TYPE,
  assistCallMode,
  callKind,
  callTypeShown,
  liveHelpActive,
  proposalDue,
  typeForMemo,
  withChannelTypes,
  MAX_PROPOSALS_PER_CALL,
  withPick,
  withProposal,
} from "./live-call-type.ts";

describe("the call type during a live call", () => {
  it("starts with Vocify's guess, shown as a proposal", () => {
    const state = withProposal(NO_CALL_TYPE, "discovery");
    assert.deepEqual(callTypeShown(state), { key: "discovery", proposed: true });
  });

  it("a later proposal replaces Vocify's guess", () => {
    const state = withProposal(withProposal(NO_CALL_TYPE, "discovery"), "closing");
    assert.deepEqual(callTypeShown(state), { key: "closing", proposed: true });
  });

  it("the rep's pick is final: proposals no longer change it", () => {
    const picked = withPick(withProposal(NO_CALL_TYPE, "discovery"), "negotiation");
    assert.deepEqual(callTypeShown(picked), { key: "negotiation", proposed: false });
    assert.deepEqual(callTypeShown(withProposal(picked, "closing")), { key: "negotiation", proposed: false });
  });

  it("'let Vocify decide' goes back to Vocify's latest proposal", () => {
    const back = withPick(withPick(withProposal(NO_CALL_TYPE, "discovery"), "closing"), null);
    assert.deepEqual(callTypeShown(back), { key: "discovery", proposed: true });
  });

  it("nothing known yet is no type, not a guess", () => {
    assert.deepEqual(callTypeShown(NO_CALL_TYPE), { key: null, proposed: false });
    assert.deepEqual(callTypeShown(withProposal(NO_CALL_TYPE, null)), { key: null, proposed: false });
  });
});

describe("proposalDue", () => {
  it("asks once the prospect has explained a little (about half a minute of talk)", () => {
    assert.equal(proposalDue({ words: 40, attempts: 0, picked: false, lastConfident: false }), false);
    assert.equal(proposalDue({ words: 80, attempts: 0, picked: false, lastConfident: false }), true);
  });

  it("asks a second time only when the first was unsure, later on", () => {
    assert.equal(proposalDue({ words: 150, attempts: 1, picked: false, lastConfident: false }), false);
    assert.equal(proposalDue({ words: 220, attempts: 1, picked: false, lastConfident: false }), true);
    assert.equal(proposalDue({ words: 220, attempts: 1, picked: false, lastConfident: true }), false);
  });

  it("never more than twice, and never once the rep picked", () => {
    assert.equal(proposalDue({ words: 5000, attempts: 2, picked: false, lastConfident: false }), false);
    assert.equal(proposalDue({ words: 5000, attempts: 0, picked: true, lastConfident: false }), false);
  });
});

describe("assistCallMode", () => {
  it("a phone call is a call for live help; anything else a meeting", () => {
    assert.equal(assistCallMode("call"), "softphone");
    assert.equal(assistCallMode("meeting"), "meeting");
    assert.equal(assistCallMode(null), "meeting");
  });
});

describe("liveHelpActive", () => {
  it("follows the remembered setting unless the rep switched it for this call", () => {
    assert.equal(liveHelpActive({ remembered: true, override: null, typeKey: "discovery" }), true);
    assert.equal(liveHelpActive({ remembered: true, override: false, typeKey: "discovery" }), false);
    assert.equal(liveHelpActive({ remembered: false, override: true, typeKey: "discovery" }), true);
  });

  it("an internal conversation has no live help", () => {
    assert.equal(liveHelpActive({ remembered: true, override: true, typeKey: "internal" }), false);
  });
});

describe("callKind", () => {
  it("the platform that caught the call decides; without one, a CRM contact on screen means a call", () => {
    assert.equal(callKind({ source: { kind: "meeting" }, contact: { hubspotId: "c-1" } }), "meeting");
    assert.equal(callKind({ source: { kind: "call" } }), "call");
    assert.equal(callKind({ source: { kind: null }, contact: { hubspotId: "c-1" } }), "call");
    assert.equal(callKind({}), "meeting");
  });

  it("the channel the rep switched to wins over the platform", () => {
    assert.equal(callKind({ channel: "call", source: { kind: "meeting" } }), "call");
    assert.equal(callKind({ channel: "meeting", contact: { hubspotId: "c-1" } }), "meeting");
  });
});

describe("the type the memo is sent with", () => {
  it("says the rep chose it only when the rep picked it", () => {
    assert.deepEqual(typeForMemo(withPick(withProposal(NO_CALL_TYPE, "discovery"), "closing")), { key: "closing", source: "rep" });
  });

  it("sends Vocify's suggestion as Vocify's, so the reading after the call can still correct it", () => {
    assert.deepEqual(typeForMemo(withProposal(NO_CALL_TYPE, "discovery")), { key: "discovery", source: "vocify" });
  });

  it("sends nothing when there is no type", () => {
    assert.equal(typeForMemo(NO_CALL_TYPE), null);
  });
});

describe("switching the channel live", () => {
  it("drops a type that is not one of the new channel's, whoever chose it", () => {
    const picked = withPick(withProposal(NO_CALL_TYPE, "cold"), "cold");
    assert.deepEqual(withChannelTypes(picked, ["demo", "internal"]), NO_CALL_TYPE);
  });

  it("keeps a type that belongs to both channels", () => {
    const state = withProposal(NO_CALL_TYPE, "follow_up");
    assert.deepEqual(withChannelTypes(state, ["follow_up", "demo"]), state);
  });

  it("never asks the model more than the cap in one call", () => {
    assert.equal(proposalDue({ words: 500, attempts: 0, picked: false, lastConfident: false, total: MAX_PROPOSALS_PER_CALL - 1 }), true);
    assert.equal(proposalDue({ words: 500, attempts: 0, picked: false, lastConfident: false, total: MAX_PROPOSALS_PER_CALL }), false);
  });
});
