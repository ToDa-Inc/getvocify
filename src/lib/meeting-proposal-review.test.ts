import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { detectedMeeting, meetingWhen } from "./meeting-proposal-review.ts";

const agreed = { agreement: "agreed", starts_at: "2026-09-29T14:00:00+00:00", timezone: "Europe/Madrid", decision: "pending" };

describe("detectedMeeting", () => {
  it("shows an agreed meeting with its time and timezone", () => {
    assert.deepEqual(detectedMeeting(agreed), { startsAt: agreed.starts_at, timezone: "Europe/Madrid" });
  });

  it("shows it whatever was clicked on it before (accepted, written, skipped)", () => {
    assert.ok(detectedMeeting({ ...agreed, decision: "accepted", crm_status: "succeeded" }));
    assert.ok(detectedMeeting({ ...agreed, decision: "omitted" }));
  });

  it("shows nothing without an agreement or without a time", () => {
    assert.equal(detectedMeeting(null), null);
    assert.equal(detectedMeeting({ ...agreed, agreement: "mentioned" }), null);
    assert.equal(detectedMeeting({ ...agreed, starts_at: null }), null);
  });
});

describe("meetingWhen", () => {
  it("formats in the meeting's own timezone, not as raw ISO", () => {
    const line = meetingWhen("2026-09-29T14:00:00+00:00", "Europe/Madrid", "es-ES");
    assert.ok(line);
    assert.match(line, /29/);
    assert.match(line, /16:00/);
    assert.equal(line.includes("T14:00"), false);
  });

  it("falls back to the local clock for an unknown timezone and hides a missing date", () => {
    assert.ok(meetingWhen("2026-09-29T14:00:00+00:00", "Not/AZone", "en-GB"));
    assert.equal(meetingWhen(null, "Europe/Madrid", "es-ES"), null);
    assert.equal(meetingWhen("garbage", "Europe/Madrid", "es-ES"), null);
  });
});
