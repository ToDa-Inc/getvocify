import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  beginMeetingListenAssist,
  resetLiveAssistOnStop,
  shouldApplyCopilotStreamPayload,
  shouldRequestLiveCopilotSuggest,
  turnOffLiveAssist,
} from "./copilot-session.js";

describe("desktop copilot session", () => {
  it("starts a meeting listen with help off and a fresh meeting id", () => {
    const session = beginMeetingListenAssist({ createMeetingId: () => "meet-a" });
    assert.equal(session.meetingId, "meet-a");
    assert.equal(session.overlay.assistEnabled, false);
    assert.equal(session.overlay.card, null);
    assert.equal(session.overlay.kind, "meeting");
    assert.equal(session.checklist, null);
    assert.equal(session.resetSuggestDedupe, true);
  });

  it("turning help off clears the card and requires aborting the stream", () => {
    const overlay = { assistEnabled: true, card: { text: "Hola" }, evidenceRefs: ["ev-1"] };
    const off = turnOffLiveAssist(overlay);
    assert.equal(off.shouldAbortSuggest, true);
    assert.equal(overlay.assistEnabled, false);
    assert.equal(overlay.card, null);
  });

  it("stop resets assist state and abort flags", () => {
    const stop = resetLiveAssistOnStop();
    assert.equal(stop.meetingId, null);
    assert.equal(stop.overlay.assistEnabled, false);
    assert.equal(stop.checklist, null);
    assert.equal(stop.shouldAbortSuggest, true);
    assert.equal(stop.shouldAbortChecklist, true);
  });

  it("ignores aborted suggest payloads and skips fetch when help is off", () => {
    assert.equal(shouldApplyCopilotStreamPayload({ signalAborted: true }), false);
    assert.equal(
      shouldRequestLiveCopilotSuggest({
        listening: true,
        assistEnabled: false,
        hasToken: true,
        latestTurn: "They: hello world",
        shouldRequestTurn: () => true,
      }),
      false,
    );
    assert.equal(
      shouldRequestLiveCopilotSuggest({
        listening: true,
        assistEnabled: true,
        hasToken: true,
        latestTurn: "They: hello world",
        shouldRequestTurn: () => false,
      }),
      false,
    );
    assert.equal(
      shouldRequestLiveCopilotSuggest({
        listening: true,
        assistEnabled: true,
        hasToken: true,
        latestTurn: "They: hello world",
        shouldRequestTurn: () => true,
      }),
      true,
    );
  });
});
