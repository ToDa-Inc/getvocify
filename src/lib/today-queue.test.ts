import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { initialQueue, queueReducer, todayQueueStart, todayQueueStep } from "./today-queue.ts";
import type { TodayItem } from "./today.ts";

const item = (reason: string, key: string): TodayItem => ({
  type: "going_cold",
  dedupe_key: key,
  reason,
  origins: ["detected"],
  supporting: [],
});

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
