import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HOME_KEYS, prefetchTarget, QUEUE_KEYS, queueKeyAction, queueReducer } from "./queue.js";

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

describe("home keys", () => {
  const MOVES = { ArrowDown: "next", j: "next", ArrowUp: "prev", k: "prev" };

  it("moves the selection with the arrows and j/k, with or without a selection", () => {
    for (const mode of ["idle", "queue", "review"]) {
      for (const [key, action] of Object.entries(MOVES)) {
        assert.equal(queueKeyAction(mode, key, {}, HOME_KEYS), action, `${mode} ${key}`);
      }
    }
  });

  it("keeps Enter, s, n and Escape as F06 defines them", () => {
    for (const [mode, map] of Object.entries(QUEUE_KEYS)) {
      for (const [key, action] of Object.entries(map)) {
        assert.equal(queueKeyAction(mode, key, {}, HOME_KEYS), action, `${mode} ${key}`);
      }
    }
    assert.equal(queueKeyAction("queue", "n", {}, HOME_KEYS), null);
    assert.equal(queueKeyAction("idle", "Enter", {}, HOME_KEYS), null);
    assert.equal(queueKeyAction("calling", "ArrowDown", {}, HOME_KEYS), null);
  });

  it("never fires inside an input, a textarea, a select or contenteditable", () => {
    const targets = [
      { tagName: "INPUT" },
      { tagName: "textarea" },
      { tagName: "SELECT" },
      { tagName: "DIV", isContentEditable: true },
    ];
    for (const target of targets) {
      for (const key of ["ArrowDown", "j", "k", "Enter", "s", "Escape"]) {
        assert.equal(queueKeyAction("queue", key, { target }, HOME_KEYS), null, `${target.tagName} ${key}`);
        assert.equal(queueKeyAction("queue", key, { target }), null, `F06 ${target.tagName} ${key}`);
      }
    }
  });

  it("never fires with Command, Control or Alt", () => {
    for (const modifier of ["metaKey", "ctrlKey", "altKey"]) {
      for (const key of ["ArrowDown", "j", "Enter", "s", "Escape"]) {
        assert.equal(queueKeyAction("queue", key, { [modifier]: true }, HOME_KEYS), null, `${modifier} ${key}`);
      }
    }
  });

  it("leaves Enter on a focused button or link to the browser", () => {
    const role = (value) => ({ tagName: "DIV", getAttribute: (name) => (name === "role" ? value : null) });
    for (const target of [{ tagName: "BUTTON" }, { tagName: "A" }, role("button"), role("link")]) {
      assert.equal(queueKeyAction("queue", "Enter", { target }, HOME_KEYS), null);
      assert.equal(queueKeyAction("queue", "ArrowDown", { target }, HOME_KEYS), "next");
    }
    assert.equal(queueKeyAction("queue", "Enter", { target: { tagName: "LI" } }, HOME_KEYS), "call");
    assert.equal(queueKeyAction("queue", "Enter", { target: { tagName: "BODY" } }, HOME_KEYS), "call");
  });

  it("runs Enter on a selectable home row after click, not the browser default", () => {
    const row = {
      tagName: "BUTTON",
      getAttribute: (name) => (name === "role" ? null : null),
      closest: (selector) => (selector === "[data-home-row]" ? row : null),
    };
    assert.equal(queueKeyAction("queue", "Enter", { target: row }, HOME_KEYS), "call");
  });
});
