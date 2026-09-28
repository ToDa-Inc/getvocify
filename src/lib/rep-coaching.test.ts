import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  STATE_VIEW,
  conversionSentence,
  durationLabel,
  focusTitle,
  focusWhy,
  formatPercent,
  hasAnyPeer,
  interactionsQuery,
  interactionsTabKey,
  peerMedianLabel,
  stateView,
  stepsDone,
  stepsDoneLine,
  trendArrow,
  trendOf,
  weekTotalLine,
  type CoachKey,
} from "./rep-coaching.ts";

const ES = productCatalog.ES;
const EN = productCatalog.EN;

describe("state view", () => {
  it("maps the four states, only done and missing count", () => {
    assert.equal(STATE_VIEW.done.glyph, "✅");
    assert.equal(STATE_VIEW.missing.glyph, "❌");
    assert.equal(STATE_VIEW.no_evidence.glyph, "❔");
    assert.equal(STATE_VIEW.not_reached.glyph, "⚪");
    assert.deepEqual(Object.entries(STATE_VIEW).filter(([, v]) => v.counted).map(([k]) => k), ["done", "missing"]);
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
  it("builds focus title, why and week total in both languages", () => {
    assert.equal(focusTitle(ES, { label: "Cierre" }), "Esta semana: Cierre");
    assert.equal(focusTitle(EN, { label: "Close" }), "This week: Close");
    const why = { rate: 0.4, applicable: 5, missing: 3, peer_median: null };
    assert.equal(focusWhy(ES, why), "3 de 5 la semana pasada sin hacerlo");
    assert.equal(weekTotalLine(ES, { done: 2, applicable: 4, rate: 0.5 }), "2 de 4 esta semana");
  });
  it("conversion sentence only when present", () => {
    assert.equal(conversionSentence(ES, null), null);
    const text = conversionSentence(ES, { complete_rate: 0.4, incomplete_rate: 0.1, complete_n: 10, incomplete_n: 20 });
    assert.match(text ?? "", /40 %.*10 %.*10 y 20/);
    assert.match(conversionSentence(EN, { complete_rate: null, incomplete_rate: 0.1, complete_n: 5, incomplete_n: 6 }) ?? "", /—/);
  });
  it("counts steps done over done + missing only", () => {
    const steps = [{ state: "done" }, { state: "done" }, { state: "missing" }, { state: "no_evidence" }, { state: "not_reached" }];
    assert.deepEqual(stepsDone(steps), { done: 2, total: 3 });
    assert.equal(stepsDoneLine(ES, steps), "Pasos hechos: 2 de 3");
    assert.equal(stepsDoneLine(ES, [{ state: "not_reached" }]), null);
    assert.equal(stepsDoneLine(ES, []), null);
  });
  it("formats duration and peer median", () => {
    assert.equal(durationLabel(ES, null), null);
    assert.equal(durationLabel(ES, 0), null);
    assert.equal(durationLabel(ES, 20), "1 min");
    assert.equal(durationLabel(ES, 300), "5 min");
    assert.equal(peerMedianLabel(ES, null), null);
    assert.equal(peerMedianLabel(ES, 0.5), "Mediana del puesto 50 %");
    assert.equal(hasAnyPeer([{ peer_median: null }]), false);
    assert.equal(hasAnyPeer([{ peer_median: null }, { peer_median: 0.2 }]), true);
  });
  it("names the interactions tab by flow", () => {
    assert.equal(interactionsTabKey("sdr"), "coachTabCalls");
    assert.equal(interactionsTabKey("ae"), "coachTabMeetings");
    assert.equal(interactionsTabKey(null), "coachTabCalls");
    assert.equal(ES.coachTabCalls, "Mis llamadas");
    assert.equal(ES.coachTabMeetings, "Mis reuniones");
  });
  it("builds the interactions query", () => {
    assert.equal(interactionsQuery({ stepId: "", state: "", meetingOnly: false }), "limit=50");
    assert.equal(
      interactionsQuery({ stepId: "s1", state: "missing", meetingOnly: true }),
      "step_id=s1&state=missing&meeting=true&limit=50",
    );
  });
});

describe("catalog", () => {
  it("has every coach key in both languages and the nav label", () => {
    const keys = Object.keys(EN).filter((k) => k.startsWith("coach") && !k.startsWith("coaching"));
    assert.ok(keys.length > 30);
    for (const key of keys) {
      assert.ok(key in ES, `ES missing ${key}`);
      assert.notEqual(String(ES[key as CoachKey]).trim(), "");
    }
    for (const view of Object.values(STATE_VIEW)) {
      assert.ok(view.labelKey in EN && view.labelKey in ES);
    }
    assert.equal(EN.navCoach, "Coaching");
    assert.equal(ES.navCoach, "Coaching");
  });
});
