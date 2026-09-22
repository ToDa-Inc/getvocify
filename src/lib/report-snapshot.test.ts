import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import { bellCount, nullableMetricLabel, reportSurface } from "./report-snapshot.ts";

describe("report snapshot", () => {
  it("does not turn a missing close into zero or add the meeting to wins", () => {
    const unavailable = productCatalog.ES.unavailable;
    const surface = reportSurface({
      metrics: { attempts: 2, connected_calls: 1, meetings_agreed: 1, deals_won: null, adherence: null },
      coverage: { crm_outcomes: "unavailable" },
      coaching: null,
    }, unavailable);
    assert.equal(surface.wonLabel, "No disponible");
    assert.equal(surface.meetings, 1);
    assert.equal(surface.coaching, null);
    assert.equal(surface.attempts, 2);
    assert.equal(surface.connected, 1);
  });

  it("hides the bell when nothing is unread and when the count is unknown", () => {
    assert.equal(bellCount(0), null);
    assert.equal(bellCount(null), null);
    assert.equal(bellCount(2), "2");
  });

  it("keeps null adherence unavailable and a real zero as zero", () => {
    const esUnavailable = productCatalog.ES.unavailable;
    const enUnavailable = productCatalog.EN.unavailable;
    assert.equal(nullableMetricLabel(null, esUnavailable), "No disponible");
    assert.equal(nullableMetricLabel(null, enUnavailable), "Not available");
    assert.equal(nullableMetricLabel(0, esUnavailable), "0");
    const surface = reportSurface({
      metrics: { attempts: 0, connected_calls: 0, meetings_agreed: 0, deals_won: null, adherence: 0 },
      coverage: { crm_outcomes: "unavailable" },
      coaching: "",
    }, esUnavailable);
    assert.equal(surface.adherenceLabel, "0");
  });
});
