import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { FOLLOWUP_POLL_FOR_MS, FOLLOWUP_POLL_MS } from "../../shared/ui/home.js";
import { afterCallLine, afterCallPoll, afterCallResolution } from "./after-call.ts";

const T0 = Date.parse("2026-09-29T10:00:00Z");

describe("after-call line", () => {
  it("stays on processing until the memo exists and has left the pipeline", () => {
    assert.deepEqual(afterCallLine(undefined, "HubSpot"), { kind: "processing" });
    assert.deepEqual(afterCallLine({ memoId: null, durationSeconds: 360 }, "HubSpot"), { kind: "processing" });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "transcribing" }, "HubSpot"), { kind: "processing" });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "extracting" }, "HubSpot"), { kind: "processing" });
  });

  it("asks for review when the memo waits for the rep", () => {
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "pending_review", durationSeconds: 360 }, "HubSpot"), {
      kind: "review",
      memoId: "m1",
      minutes: 6,
    });
  });

  it("says saved only once the memo is approved", () => {
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "approved", durationSeconds: 360 }, "HubSpot"), {
      kind: "saved",
      minutes: 6,
    });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "approved" }, "HubSpot"), { kind: "saved", minutes: null });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "failed", durationSeconds: 360 }, "HubSpot"), {
      kind: "duration",
      minutes: 6,
    });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "rejected", durationSeconds: 360 }, "HubSpot"), {
      kind: "duration",
      minutes: 6,
    });
    assert.deepEqual(afterCallLine({ memoId: "m1", memoStatus: "approved", durationSeconds: 360 }, null), {
      kind: "duration",
      minutes: 6,
    });
    assert.equal(afterCallLine({ memoId: "m1", memoStatus: "failed" }, "HubSpot"), null);
  });
});

describe("after-call resolution", () => {
  it("advances on voicemail or no response and stays on a failed call", () => {
    assert.equal(afterCallResolution({ memoId: "m1", screeningOutcome: "voicemail" }), "no_answer");
    assert.equal(afterCallResolution({ memoId: "m1", screeningOutcome: "no_response" }), "no_answer");
    assert.equal(afterCallResolution({ status: "failed" }), "failed");
    assert.equal(afterCallResolution({ memoId: "m1", screeningOutcome: "connected" }), null);
    assert.equal(afterCallResolution(undefined), null);
  });
});

describe("after-call poll", () => {
  it("polls at the home cadence while processing, still after 60 s, and stops at the home bound", () => {
    const first = afterCallPoll(undefined, null, T0);
    assert.deepEqual(first, { interval: FOLLOWUP_POLL_MS, since: T0 });
    const minute = afterCallPoll({ memoId: null }, T0, T0 + 61_000);
    assert.deepEqual(minute, { interval: FOLLOWUP_POLL_MS, since: T0 });
    assert.deepEqual(afterCallLine({ memoId: null }, "HubSpot"), { kind: "processing" });
    assert.deepEqual(afterCallPoll({ memoId: null }, T0, T0 + FOLLOWUP_POLL_FOR_MS + 1), { interval: false, since: T0 });
  });

  it("stops once the call is settled", () => {
    assert.deepEqual(afterCallPoll({ memoId: "m1", memoStatus: "pending_review" }, T0, T0 + 5000), { interval: false, since: null });
    assert.deepEqual(afterCallPoll({ memoId: "m1", memoStatus: "approved" }, T0, T0 + 5000), { interval: false, since: null });
    assert.deepEqual(afterCallPoll({ screeningOutcome: "voicemail" }, T0, T0 + 5000), { interval: false, since: null });
    assert.deepEqual(afterCallPoll({ status: "failed" }, T0, T0 + 5000), { interval: false, since: null });
  });
});
