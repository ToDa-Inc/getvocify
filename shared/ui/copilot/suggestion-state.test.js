import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  assistAllowed,
  copilotLiveAssistAllowed,
  overlayAssist,
  pushSse,
  reduceSuggestion,
  resolveLiveAssistKind,
  stepStatus,
} from "./suggestion-state.js";

describe("live meeting assist", () => {
  it("shows meeting help on the overlay and keeps a call on the transcript line", () => {
    assert.equal(overlayAssist({ kind: "call", playbookReady: true, evidenceRefs: ["ev-1"], card: { text: "Pregunta el precio" } }), null);
    assert.equal(overlayAssist({ kind: "meeting", playbookReady: true, evidenceRefs: [], card: { text: "Pregunta el precio" } }), null);
    assert.equal(overlayAssist({
      kind: "meeting",
      playbookReady: true,
      evidenceRefs: ["ev-1"],
      card: { text: "Pregunta el precio" },
    }), "Pregunta el precio");
  });

  it("hides the extension copilot card on a call even with coaching text queued", () => {
    assert.equal(
      copilotLiveAssistAllowed({
        kind: "call",
        playbookReady: true,
        evidenceRefs: ["ev-1"],
        callActive: false,
        captureIsMeetingApp: false,
      }).show,
      false,
    );
    assert.equal(
      copilotLiveAssistAllowed({
        playbookReady: true,
        evidenceRefs: ["ev-1"],
        callActive: true,
        captureIsMeetingApp: true,
      }).reason,
      "not_a_meeting",
    );
    assert.equal(
      copilotLiveAssistAllowed({
        kind: "meeting",
        playbookReady: true,
        evidenceRefs: ["ev-1"],
        callActive: false,
        captureIsMeetingApp: false,
      }).show,
      true,
    );
    assert.equal(resolveLiveAssistKind({ captureIsMeetingApp: true }), "meeting");
    assert.equal(resolveLiveAssistKind({ callActive: true, captureIsMeetingApp: true }), "call");
  });

  it("stays hidden on a call and when there is nothing to ground a card", () => {
    assert.equal(assistAllowed({ kind: "call", enabled: true, playbookReady: true, evidenceRefs: ["ev-1"] }).reason, "not_a_meeting");
    assert.equal(assistAllowed({ kind: "meeting", enabled: false, playbookReady: true, evidenceRefs: ["ev-1"] }).show, false);
    const silent = assistAllowed({ kind: "meeting", enabled: true, playbookReady: false, evidenceRefs: [] });
    assert.equal(silent.show, false);
    assert.equal(silent.reason, "silent");
  });

  it("marks a step only from evidence, not from elapsed time", () => {
    const step = { id: "ask-price", evidence_ref: "ev-1" };
    assert.equal(stepStatus(step, [], 120000), "open");
    assert.equal(stepStatus(step, ["ev-1"], 0), "done");
  });

  it("drops a late result when the meeting changed and parses a split SSE frame once", () => {
    let state = reduceSuggestion({ meetingId: null, requestId: null, card: null }, { type: "start", meetingId: "meet-1" });
    state = reduceSuggestion(state, { type: "request", meetingId: "meet-1", requestId: "sug-3" });
    state = reduceSuggestion(state, { type: "switch", meetingId: "meet-2" });
    const stale = reduceSuggestion(state, {
      type: "result",
      meetingId: "meet-1",
      requestId: "sug-3",
      card: { text: "vieja" },
    });
    assert.equal(stale.card, null);
    assert.equal(stale.meetingId, "meet-2");
    const split = pushSse("", 'data: {"event":"result"}\n');
    assert.deepEqual(split.events, []);
    const closed = pushSse(split.buffer, "\n");
    assert.deepEqual(closed.events, ['{"event":"result"}']);
  });
});
