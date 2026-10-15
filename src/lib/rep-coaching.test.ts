import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  STATE_VIEW,
  cleanSummaryLine,
  countTone,
  durationLabel,
  focusTitle,
  formatPercent,
  peerMedianLabel,
  stateView,
  summarizeCalls,
  trendArrow,
  trendOf,
  weekTotalLine,
  type CoachKey,
} from "./rep-coaching.ts";

const ES = productCatalog.ES;
const EN = productCatalog.EN;

describe("state view", () => {
  it("maps the five states; done, could-be-better and missing count", () => {
    assert.equal(STATE_VIEW.done.glyph, "✅");
    assert.equal(STATE_VIEW.improvable.glyph, "🟡");
    assert.equal(STATE_VIEW.missing.glyph, "❌");
    assert.equal(STATE_VIEW.no_evidence.glyph, "❔");
    assert.equal(STATE_VIEW.not_reached.glyph, "⚪");
    assert.deepEqual(Object.entries(STATE_VIEW).filter(([, v]) => v.counted).map(([k]) => k), ["done", "improvable", "missing"]);
    assert.equal(stateView("weird").glyph, "❔");
  });
});

describe("formatPercent / trend", () => {
  it("shows a dash for null, never 0", () => {
    assert.equal(formatPercent(null), "—");
    assert.equal(formatPercent(undefined), "—");
    assert.equal(formatPercent(0), "0 %");
    assert.equal(formatPercent(0.626), "63 %");
  });
  it("uses a 5-point dead band", () => {
    assert.equal(trendOf(0.7, 0.5), "up");
    assert.equal(trendOf(0.4, 0.5), "down");
    assert.equal(trendOf(0.54, 0.5), "flat");
    assert.equal(trendOf(0.55, 0.5), "flat");
    assert.equal(trendOf(0.46, 0.5), "flat");
    assert.equal(trendOf(null, 0.5), null);
    assert.equal(trendOf(0.5, null), null);
    assert.equal(trendArrow("up"), "↑");
    assert.equal(trendArrow("down"), "↓");
    assert.equal(trendArrow("flat"), "→");
    assert.equal(trendArrow(null), "");
  });
});

describe("sentences", () => {
  it("builds the focus title and week total Ask's coaching card shows", () => {
    assert.equal(focusTitle(ES, { label: "Cierre" }), "Esta semana: Cierre");
    assert.equal(focusTitle(EN, { label: "Close" }), "This week: Close");
    assert.equal(weekTotalLine(ES, { done: 2, applicable: 4, rate: 0.5 }), "2 de 4 esta semana");
  });
  it("tones a count as all, none or some", () => {
    assert.equal(countTone(3, 3), "success");
    assert.equal(countTone(0, 4), "destructive");
    assert.equal(countTone(2, 4), "warning");
    assert.equal(countTone(0, 0), "muted");
  });
  it("cleans the markdown the extraction leaves in a summary", () => {
    assert.equal(cleanSummaryLine("Resultado:** Sin conversación."), "Sin conversación.");
    assert.equal(cleanSummaryLine("Dijo que **no** ve prioridad"), "Dijo que no ve prioridad");
    assert.equal(cleanSummaryLine(null), "");
  });
  it("formats duration and peer median", () => {
    assert.equal(durationLabel(ES, null), null);
    assert.equal(durationLabel(ES, 0), null);
    assert.equal(durationLabel(ES, 20), "1 min");
    assert.equal(durationLabel(ES, 300), "5 min");
    assert.equal(peerMedianLabel(ES, null), null);
    assert.equal(peerMedianLabel(ES, 0.5), "Mediana del puesto 50 %");
  });
});

describe("catalog", () => {
  it("has every coach key in both languages and the nav label", () => {
    const keys = Object.keys(EN).filter((k) => k.startsWith("coach") && !k.startsWith("coaching"));
    assert.ok(keys.length > 20);
    for (const key of keys) {
      assert.ok(key in ES, `ES missing ${key}`);
      assert.notEqual(String(ES[key as CoachKey]).trim(), "");
    }
    for (const view of Object.values(STATE_VIEW)) {
      assert.ok(view.labelKey in EN && view.labelKey in ES);
    }
    assert.equal(EN.navCoach, "Coaching");
    assert.equal(ES.navCoach, "Coaching");
    assert.equal(ES.coachCallsHeading, "Tus conversaciones");
  });
});

describe("summarizeCalls", () => {
  const day = 24 * 3600 * 1000;
  const now = Date.parse("2026-10-15T12:00:00Z");
  const call = (daysAgo: number, done: number, applicable: number, extra = {}) => ({
    observed_at: new Date(now - daysAgo * day).toISOString(), kind: "call", done, applicable, meeting_agreed: false, ...extra,
  });

  it("counts conversations by channel and the process done over what was judged", () => {
    const out = summarizeCalls([call(1, 3, 6), call(2, 1, 4, { kind: "meeting" }), call(3, 0, 0, { meeting_agreed: true })], now);
    assert.equal(out.conversations, 3);
    assert.deepEqual(out.byKind, { call: 2, meeting: 1 });
    assert.equal(out.rate, 4 / 10);
    assert.equal(out.meetings, 1);
  });

  it("has no rate when nothing was judged", () => {
    assert.equal(summarizeCalls([call(1, 0, 0)], now).rate, null);
    assert.equal(summarizeCalls([], now).rate, null);
  });

  it("compares the last two weeks with the two before only with three calls on each side", () => {
    const recent = [call(1, 5, 10), call(3, 5, 10), call(5, 5, 10)];
    const before = [call(15, 2, 10), call(18, 2, 10), call(20, 2, 10)];
    const out = summarizeCalls([...recent, ...before], now);
    assert.deepEqual(out.recent, { rate: 0.5, prev: 0.2 });
    assert.equal(summarizeCalls([...recent, before[0]], now).recent, null);
  });
});
