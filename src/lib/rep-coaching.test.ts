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
  improveBeforeLine,
  improveCountLine,
  peerMedianLabel,
  stateView,
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

describe("what to improve", () => {
  it("counts the slips, never a %: not done first, halfway after", () => {
    assert.equal(improveCountLine(ES, { missing: 4, improvable: 0, applicable: 9 }), "No lo hiciste en 4 de 9 conversaciones");
    assert.equal(improveCountLine(ES, { missing: 4, improvable: 2, applicable: 9 }), "No lo hiciste en 4 de 9 conversaciones · a medias en 2");
    assert.equal(improveCountLine(ES, { missing: 0, improvable: 3, applicable: 5 }), "A medias en 3 de 5 conversaciones");
    assert.equal(improveCountLine(EN, { missing: 1, improvable: 1, applicable: 3 }), "Not done in 1 of 3 conversations · halfway in 1");
  });
  it("compares only with the rep's own weeks before, and says nothing without calls then", () => {
    const item = (missing: number, improvable: number, applicable: number) => ({ before: { missing, improvable, applicable } });
    assert.equal(improveBeforeLine(ES, item(3, 11, 14), 4), "Las 4 semanas anteriores: no lo hiciste en 3 de 14 conversaciones · a medias en 11");
    assert.equal(improveBeforeLine(EN, item(0, 2, 5), 4), "The 4 weeks before: done halfway in 2 of 5 conversations");
    assert.equal(improveBeforeLine(ES, item(0, 0, 0), 4), null);
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
    assert.equal(ES.coachCallsHeading, "Tus llamadas");
  });
});
