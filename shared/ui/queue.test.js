import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { prefetchTarget, queueKeyAction, queueReducer } from "./queue.js";

const state = { mode: "calling", items: [{ id: "a" }, { id: "b" }], index: 0 };

describe("queue", () => {
  it("advances a voicemail even when a memo exists", () => {
    const next = queueReducer(state, {
      type: "call_ended",
      memoId: "voicemail-memo",
      screeningOutcome: "voicemail",
    });
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 1);
    assert.equal(next.memoId, undefined);
    const quiet = queueReducer(state, {
      type: "call_ended",
      memoId: "quiet-memo",
      screeningOutcome: "no_response",
    });
    assert.equal(quiet.index, 1);
    assert.equal(quiet.mode, "queue");
  });

  it("opens review of the conversation memo", () => {
    const next = queueReducer(state, {
      type: "call_ended",
      memoId: "memo-conversation",
      screeningOutcome: "connected",
    });
    assert.equal(next.mode, "review");
    assert.equal(next.memoId, "memo-conversation");
    assert.equal(next.index, 0);
  });

  it("keeps a failed call on the same contact without a success", () => {
    const next = queueReducer(state, { type: "call_ended", callStatus: "failed", memoId: "memo-x" });
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 0);
    assert.equal(next.lastOutcome, "failed");
    assert.equal(next.mode === "done", false);
  });

  it("prefetches the next contact and does not invent a brief", () => {
    const target = prefetchTarget(state);
    assert.deepEqual(target, { id: "b" });
    assert.equal("blocks" in target, false);
  });

  it("maps queue keyboard shortcuts without modifier keys", () => {
    assert.equal(queueKeyAction("queue", "Enter"), "call");
    assert.equal(queueKeyAction("queue", "s"), "skip");
    assert.equal(queueKeyAction("queue", "Escape"), "exit");
    assert.equal(queueKeyAction("review", "n"), "reviewed");
    assert.equal(queueKeyAction("queue", "Enter", { metaKey: true }), null);
  });
});
