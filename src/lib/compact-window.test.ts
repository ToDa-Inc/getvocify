import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { compactViewShown, compactWindowReleased } from "./compact-window.ts";

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
});
