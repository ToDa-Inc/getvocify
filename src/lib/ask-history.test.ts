import assert from "node:assert/strict";
import test from "node:test";
import { groupByDay } from "./ask-history.ts";

const now = new Date(2026, 8, 29, 15, 0);
const at = (daysAgo: number, hour = 9) => new Date(2026, 8, 29 - daysAgo, hour).toISOString();

test("conversations group into today, yesterday, this week and older, in that order", () => {
  const rows = [
    { id: "a", updated_at: at(0, 14) }, { id: "b", updated_at: at(0, 8) }, { id: "c", updated_at: at(1) },
    { id: "d", updated_at: at(3) }, { id: "e", updated_at: at(6) }, { id: "f", updated_at: at(7) }, { id: "g", updated_at: null },
  ];
  const groups = groupByDay(rows, now);
  assert.deepEqual(groups.map((g) => g.key), ["today", "yesterday", "week", "older"]);
  assert.deepEqual(groups.map((g) => g.rows.map((r) => r.id)), [["a", "b"], ["c"], ["d", "e"], ["f", "g"]]);
});

test("empty groups are left out", () => {
  assert.deepEqual(groupByDay([{ updated_at: at(0) }], now).map((g) => g.key), ["today"]);
  assert.deepEqual(groupByDay([], now), []);
});
