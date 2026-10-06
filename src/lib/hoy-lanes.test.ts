import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { motionsFor, splitByLane, visibleLanes } from "./hoy-lanes.ts";

describe("visibleLanes", () => {
  it("locks a member to one lane and lets an admin see both", () => {
    assert.deepEqual(visibleLanes("sdr", "member"), ["calls"]);
    assert.deepEqual(visibleLanes("ae", "member"), ["meetings"]);
    assert.deepEqual(visibleLanes("general", "member"), ["calls", "meetings"]);
    assert.deepEqual(visibleLanes("sdr", "admin"), ["calls", "meetings"]);
  });
});

describe("motionsFor", () => {
  it("hides closing from an SDR and prospecting from an AE", () => {
    assert.deepEqual(motionsFor("sdr", "member"), ["discovery", "qualification"]);
    assert.deepEqual(motionsFor("ae", "member"), ["closing"]);
    assert.deepEqual(motionsFor("ae", "owner"), ["discovery", "qualification", "closing"]);
  });
});

describe("splitByLane", () => {
  it("puts unlabeled items in calls", () => {
    const split = splitByLane([{ id: "a" }, { id: "b", lane: "meetings" }, { id: "c", lane: "calls" }]);
    assert.deepEqual(split.calls.map((item) => item.id), ["a", "c"]);
    assert.deepEqual(split.meetings.map((item) => item.id), ["b"]);
  });
});
