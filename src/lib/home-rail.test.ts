import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { HomeSection } from "@shared/ui/home.js";
import type { TodayItem } from "./today.ts";
import { RAIL_MEETINGS, railCounts } from "./home-rail.ts";

function item(id: string, overrides: Partial<TodayItem> = {}): TodayItem {
  return { type: "meeting_today", dedupe_key: id, id, reason: id, origins: [], supporting: [], ...overrides };
}

function meeting(id: string, dueAt: string | null, past = false) {
  return { item: item(id, { due_at: dueAt, precision: dueAt ? "time" : "date" }), time: dueAt ? dueAt.slice(11, 16) : null, past };
}

function cards(count: number, prefix: string) {
  return Array.from({ length: count }, (_, index) => ({ source: "today" as const, item: item(`${prefix}${index}`, { type: "manual_task" }) }));
}

describe("railCounts", () => {
  it("returns nothing due for a home with no sections", () => {
    assert.deepEqual(railCounts({ sections: [] }), {
      meetings: [],
      needsOk: 0,
      tasks: 0,
      followups: 0,
      fresh: 0,
      calls: 0,
    });
  });

  it("keeps at most three meetings, the soonest first, demos and meetings together", () => {
    const sections: HomeSection[] = [
      { id: "demos", items: [meeting("d-16", "2026-09-30T16:00:00Z"), meeting("d-09", "2026-09-30T09:00:00Z")] },
      { id: "meetings", items: [meeting("m-12", "2026-09-30T12:00:00Z"), meeting("m-11", "2026-09-30T11:00:00Z")] },
    ];
    const out = railCounts({ sections });
    assert.equal(RAIL_MEETINGS, 3);
    assert.deepEqual(
      out.meetings.map((entry) => entry.item.id),
      ["d-09", "m-11", "m-12"],
    );
  });

  it("puts a meeting that already started after the ones still to come, and one without a time after timed ones", () => {
    const sections: HomeSection[] = [
      {
        id: "meetings",
        items: [meeting("past-08", "2026-09-30T08:00:00Z", true), meeting("no-time", null), meeting("next-15", "2026-09-30T15:00:00Z")],
      },
    ];
    assert.deepEqual(
      railCounts({ sections }).meetings.map((entry) => entry.item.id),
      ["next-15", "no-time", "past-08"],
    );
  });

  it("counts each section; a group of confirmations counts every card in it", () => {
    const sections: HomeSection[] = [
      { id: "tasks", items: cards(4, "t") },
      {
        id: "needs_ok",
        rows: [
          { kind: "confirm_group", count: 3, items: [item("c1"), item("c2"), item("c3")], action: "expand" },
          { kind: "followup", memoId: "m1", contactId: null, name: null, subject: null, status: "ready", action: "open" },
          { kind: "review", memoId: "m2", contactId: null, name: null, action: "review" },
        ],
        shown: [],
        more: 0,
      },
      { id: "followups", items: cards(2, "f") },
      { id: "new", items: cards(7, "n") },
      { id: "upcoming", rows: [] },
    ];
    const out = railCounts({ sections });
    assert.equal(out.tasks, 4);
    assert.equal(out.needsOk, 5);
    assert.equal(out.followups, 2);
    assert.equal(out.fresh, 7);
    assert.equal(out.calls, 0);
  });

  it("counts single confirmations one by one and the unsectioned calls list", () => {
    const sections: HomeSection[] = [
      { id: "needs_ok", rows: [{ kind: "confirm", item: item("c1"), action: "confirm" }], shown: [], more: 0 },
      { id: "calls", items: cards(6, "k") },
    ];
    const out = railCounts({ sections });
    assert.equal(out.needsOk, 1);
    assert.equal(out.calls, 6);
    assert.equal(out.tasks, 0);
  });
});
