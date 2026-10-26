import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { compactViewShown, compactWindowDue, compactWindowReleased } from "./compact-window.ts";

describe("the compact window", () => {
  it("covers the dashboard only while a call is on", () => {
    assert.equal(compactViewShown(true, "live"), true);
    assert.equal(compactViewShown(true, "starting"), true);
    assert.equal(compactViewShown(false, "live"), false);
    assert.equal(compactViewShown(true, "stopping"), false);
  });

  it("goes back to its size once the call is over, so the review shows as always", () => {
    for (const phase of ["stopping", "uploading", "idle"] as const) assert.equal(compactWindowReleased(true, phase), true);
    assert.equal(compactWindowReleased(true, "live"), false);
    assert.equal(compactWindowReleased(false, "idle"), false);
  });

  it("comes by itself when a recording goes live, once per call", () => {
    const base = { available: true, phase: "live" as const, callId: "c1", doneFor: null };
    assert.equal(compactWindowDue(base), true);
    assert.equal(compactWindowDue({ ...base, doneFor: "c1" }), false, "the rep opened the whole dashboard: it stays open");
    assert.equal(compactWindowDue({ ...base, doneFor: "c1", callId: "c2" }), true, "the next call is compact again");
    assert.equal(compactWindowDue({ ...base, phase: "starting" }), false);
    assert.equal(compactWindowDue({ ...base, available: false }), false, "an app that cannot resize its window");
    assert.equal(compactWindowDue({ ...base, callId: null }), false);
  });
});
