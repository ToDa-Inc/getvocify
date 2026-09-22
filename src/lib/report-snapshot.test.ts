import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { reportSurface } from "./report-snapshot.ts";

describe("report snapshot", () => {
  it("does not turn a missing close into zero or add the meeting to wins", () => {
    const surface = reportSurface({
      metrics: { attempts: 2, connected_calls: 1, meetings_agreed: 1, deals_won: null, adherence: null },
      coverage: { crm_outcomes: "unavailable" },
      coaching: null,
    });
    assert.equal(surface.wonLabel, "No disponible");
    assert.equal(surface.meetings, 1);
    assert.equal(surface.coaching, null);
    assert.equal(surface.attempts, 2);
    assert.equal(surface.connected, 1);
  });
});
