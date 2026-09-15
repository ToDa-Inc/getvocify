import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ACTIVITY_EXPAND_SIZE,
  ACTIVITY_PAGE_SIZE,
  activityEmptyMessage,
  mergeActivityItems,
  nextVisibleCount,
  shouldPeekNextActivity,
} from "./activity-feed.ts";

describe("mergeActivityItems", () => {
  it("mixes recordings and memos newest first and skips recordings without audio", () => {
    const items = mergeActivityItems({
      recordings: [
        {
          call_id: "c-old",
          title: "Old call",
          has_recording: true,
          timestamp: "2026-08-01T10:00:00.000Z",
        },
        {
          call_id: "c-skip",
          title: "Skip",
          has_recording: false,
          timestamp: "2026-08-19T10:00:00.000Z",
        },
        {
          call_id: "c-new",
          title: "New call",
          memo_id: "dup",
          has_recording: true,
          timestamp_ms: Date.parse("2026-08-18T12:00:00.000Z"),
        },
      ],
      memos: [
        { id: "memo-mid", createdAt: "2026-08-10T09:00:00.000Z" },
        { id: "dup", createdAt: "2026-08-19T09:00:00.000Z" },
      ],
    });
    assert.deepEqual(
      items.map((item) => item.id),
      ["c-new", "memo-mid", "c-old"],
    );
    assert.deepEqual(
      items.map((item) => item.kind),
      ["recording", "memo", "recording"],
    );
  });

  it("still lists a HubSpot call memo when there is no playable recording", () => {
    const items = mergeActivityItems({
      recordings: [
        {
          call_id: "c1",
          title: "Call",
          memo_id: "m-hs",
          has_recording: false,
          timestamp: "2026-08-19T10:00:00.000Z",
        },
      ],
      memos: [{ id: "m-hs", createdAt: "2026-08-19T10:00:00.000Z" }],
    });
    assert.deepEqual(
      items.map((item) => item.id),
      ["m-hs"],
    );
    assert.equal(items[0].kind, "memo");
  });

  it("dedupes a memo already joined via HubSpot engagement id", () => {
    const items = mergeActivityItems({
      recordings: [
        {
          call_id: "1169",
          title: "Llamada Vocify",
          has_recording: true,
          timestamp: "2026-09-15T10:00:00.000Z",
        },
      ],
      memos: [
        {
          id: "memo-1",
          createdAt: "2026-09-15T10:00:00.000Z",
          hubspotEngagementId: "1169",
        },
      ],
    });
    assert.deepEqual(
      items.map((item) => item.id),
      ["1169"],
    );
    assert.equal(items[0].kind, "recording");
  });
});

describe("activity pagination", () => {
  it("starts collapsed at three rows and expands by five", () => {
    assert.equal(ACTIVITY_PAGE_SIZE, 3);
    assert.equal(ACTIVITY_EXPAND_SIZE, 5);
    assert.equal(nextVisibleCount(3, 20), 8);
    assert.equal(nextVisibleCount(8, 20), 13);
    assert.equal(nextVisibleCount(18, 20), 20);
  });

  it("peeks the next row only while the list is still collapsed", () => {
    assert.equal(shouldPeekNextActivity(3, 8), true);
    assert.equal(shouldPeekNextActivity(8, 20), false);
    assert.equal(shouldPeekNextActivity(3, 3), false);
  });
});

describe("activityEmptyMessage", () => {
  it("adapts copy for teammate, mine, and first-run", () => {
    assert.equal(
      activityEmptyMessage({ viewingTeammate: true, mine: false, canViewCompany: true }),
      "No activity for this teammate. Try All to see every labeled conversation.",
    );
    assert.equal(
      activityEmptyMessage({ viewingTeammate: false, mine: true, canViewCompany: true }),
      "No activity of yours yet. Try All to see every labeled conversation.",
    );
    assert.equal(
      activityEmptyMessage({ viewingTeammate: false, mine: false, canViewCompany: false }),
      "No activity yet. Record your first one above.",
    );
  });
});
