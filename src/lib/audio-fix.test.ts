import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isBrokenGrant, nextCallAudioFix } from "./audio-fix.ts";

describe("nextCallAudioFix", () => {
  it("starts with switching Vocify off and on", () => {
    assert.deepEqual(nextCallAudioFix(null, "failed"), { step: "toggle", relaunched: false });
  });

  it("keeps the step while the rep hasn't relaunched yet", () => {
    assert.deepEqual(nextCallAudioFix({ step: "toggle", relaunched: false }, "failed"), { step: "toggle", relaunched: false });
  });

  it("moves to removing and re-adding Vocify when a relaunch didn't fix it", () => {
    const relaunched = nextCallAudioFix({ step: "toggle", relaunched: false }, "relaunching");
    assert.deepEqual(relaunched, { step: "toggle", relaunched: true });
    assert.deepEqual(nextCallAudioFix(relaunched, "failed"), { step: "readd", relaunched: false });
  });

  it("clears once a capture works", () => {
    assert.equal(nextCallAudioFix({ step: "readd", relaunched: true }, "worked"), null);
  });

  it("does nothing on relaunch when nothing was broken", () => {
    assert.equal(nextCallAudioFix(null, "relaunching"), null);
  });
});

describe("isBrokenGrant", () => {
  it("counts a capture that failed while allowed", () => {
    assert.equal(isBrokenGrant("capture_failed"), true);
    assert.equal(isBrokenGrant("helper_timeout"), true);
    assert.equal(isBrokenGrant(undefined), true);
  });

  it("leaves an off switch and a busy capture to their own handling", () => {
    for (const reason of ["permission_denied", "needs_restart", "already_running", "unsupported_platform"]) {
      assert.equal(isBrokenGrant(reason), false, reason);
    }
  });
});
