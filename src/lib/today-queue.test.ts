import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { initialHomeSelection, homeSelection, homeRows, selectedRow } from "../../shared/ui/home.js";
import {
  homeQueueCallEnded,
  homeQueueCallResolved,
  homeQueueReviewed,
  homeQueueStartCall,
  homeQueueLocked,
  homeQueueInReview,
  todayQueueStart,
  todayQueueStep,
  initialQueue,
  queueReducer,
} from "./today-queue.ts";
import type { TodayItem } from "./today.ts";

const item = (reason: string, key: string): TodayItem => ({
  type: "going_cold",
  dedupe_key: key,
  reason,
  origins: ["detected"],
  supporting: [],
});

const rowKeys = ["hoy:a", "hoy:b", "hoy:c"];
const inQueue = { mode: "queue" as const, items: rowKeys, index: 0, touched: true };
const calling = { mode: "calling" as const, items: rowKeys, index: 0, touched: true };

describe("today queue adapter", () => {
  it("start then skip advances; exit returns to idle", () => {
    const items = [item("first", "a"), item("second", "b")];
    let state = todayQueueStart(items);
    assert.equal(state.mode, "queue");
    assert.equal(state.index, 0);

    state = todayQueueStep(state, { type: "skip" });
    assert.equal(state.mode, "queue");
    assert.equal(state.index, 1);

    state = todayQueueStep(state, { type: "exit" });
    assert.deepEqual(state, initialQueue);
  });

  it("after done, start returns to the first item", () => {
    const items = [item("first", "a"), item("second", "b")];
    let state = todayQueueStart(items);
    state = todayQueueStep(state, { type: "skip" });
    state = todayQueueStep(state, { type: "skip" });
    assert.equal(state.mode, "done");

    state = queueReducer(state, { type: "start", items });
    assert.equal(state.mode, "queue");
    assert.equal(state.index, 0);
  });
});

describe("home queue call lifecycle", () => {
  it("enters calling from queue and locks selection", () => {
    const next = homeQueueStartCall(inQueue);
    assert.equal(next.mode, "calling");
    assert.equal(homeQueueLocked(next), true);
    assert.equal(homeQueueLocked(homeSelection(next, { type: "next" })), true);
    assert.equal(homeSelection(next, { type: "next" }).index, 0);
  });

  it("opens review after a conversation ends", () => {
    const next = homeQueueCallEnded(calling, {
      memoId: "memo-1",
      screeningOutcome: "connected",
    });
    assert.equal(next.mode, "review");
    assert.equal(next.memoId, "memo-1");
    assert.equal(next.index, 0);
    assert.equal(homeQueueInReview(next), true);
  });

  it("advances on voicemail or no response without review", () => {
    const voicemail = homeQueueCallEnded(calling, {
      memoId: "memo-vm",
      screeningOutcome: "voicemail",
    });
    assert.equal(voicemail.mode, "queue");
    assert.equal(voicemail.index, 1);
    assert.equal(voicemail.lastOutcome, "no_answer");

    const quiet = homeQueueCallEnded(calling, {
      memoId: "memo-nr",
      screeningOutcome: "no_response",
    });
    assert.equal(quiet.mode, "queue");
    assert.equal(quiet.index, 1);
    assert.equal(quiet.lastOutcome, "no_answer");
  });

  it("stays on the same contact when the call failed", () => {
    const next = homeQueueCallEnded(calling, { callStatus: "failed", memoId: "memo-x" });
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 0);
    assert.equal(next.lastOutcome, "failed");
  });

  it("moves to the next row when review finishes with n", () => {
    const review = homeQueueCallEnded(calling, { memoId: "memo-1" });
    const next = homeQueueReviewed(review);
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 1);
    assert.equal(homeQueueInReview(next), false);
  });

  it("No conecta: a call that never connected stays on the same contact as failed", () => {
    const next = homeQueueCallEnded(calling, { answered: false, callSid: "CA1" });
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 0);
    assert.equal(next.lastOutcome, "failed");
  });

  it("Procesado > 60 s: an answered call reviews without a memo and n still moves on", () => {
    const review = homeQueueCallEnded(calling, { answered: true, callSid: "CA2" });
    assert.equal(review.mode, "review");
    assert.equal(review.memoId, undefined);
    assert.equal(homeQueueReviewed(review).index, 1);
  });

  it("a processed voicemail leaves review, advances and names the row to note", () => {
    const review = homeQueueCallEnded(calling, { answered: true, callSid: "CA3" });
    const next = homeQueueCallResolved(review, { outcome: "no_answer", callSid: "CA3" });
    assert.equal(next.mode, "queue");
    assert.equal(next.index, 1);
    assert.deepEqual(next.lastCall, { key: "hoy:a", outcome: "no_answer" });
  });

  it("leaves nothing selected when n is pressed on the last row in review", () => {
    const last = { mode: "calling" as const, items: rowKeys, index: 2, touched: true };
    const review = homeQueueCallEnded(last, { memoId: "memo-9" });
    const next = homeQueueReviewed(review);
    assert.equal(next.mode, "done");
    assert.equal(selectedRow(next, []), null);
  });
});
