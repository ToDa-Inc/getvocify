import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  STATE_VIEW,
  stepCountLine,
  canPickFlow,
  conversionSentence,
  isGeneralRep,
  latestSelfReportId,
  meetingsTileKey,
  viewingFlowKey,
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
  rateOrCount,
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

  it("shows the counts behind a rate, and what could be better", () => {
    assert.equal(stepCountLine(ES, { done: 0, applicable: 1 }), "0 de 1");
    assert.equal(stepCountLine(ES, { done: 2, improvable: 1, applicable: 3 }), "2 de 3 · 1 mejorable(s)");
    assert.equal(stepCountLine(ES, {}), null);
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

describe("flow-aware copy and toggle", () => {
  const conv = { complete_rate: 0.4, incomplete_rate: 0.1, complete_n: 10, incomplete_n: 20 };
  it("keeps the SDR conversion sentence and reframes the AE one", () => {
    assert.match(conversionSentence(ES, conv, "sdr") ?? "", /acordaste reunión en el 40 % de las conversaciones.*10 y 20 conversaciones/);
    assert.equal(conversionSentence(ES, conv), conversionSentence(ES, conv, "sdr"));
    assert.equal(
      conversionSentence(ES, conv, "ae"),
      "Siguiendo el proceso completo cerraste siguiente reunión en el 40 % de las reuniones; sin él, en el 10 % (10 y 20 reuniones).",
    );
    assert.match(conversionSentence(EN, conv, "ae") ?? "", /next meeting in 40 % of meetings; without it, 10 % \(10 and 20 meetings\)/);
    assert.equal(conversionSentence(ES, null, "ae"), null);
  });
  it("names the meetings tile by flow", () => {
    assert.equal(meetingsTileKey("sdr"), "coachNumMeetings");
    assert.equal(ES.coachNumMeetings, "Reuniones acordadas");
    assert.equal(meetingsTileKey("ae"), "coachNumMeetingsAe");
    assert.equal(ES.coachNumMeetingsAe, "Siguiente reunión acordada");
    assert.equal(EN.coachNumMeetingsAe, "Next meeting agreed");
  });
  it("shows the toggle only to general reps with both flows", () => {
    assert.equal(isGeneralRep(null), true);
    assert.equal(isGeneralRep(undefined), true);
    assert.equal(isGeneralRep("general"), true);
    assert.equal(isGeneralRep("sdr"), false);
    assert.equal(canPickFlow(null, ["sdr", "ae"]), true);
    assert.equal(canPickFlow("general", ["sdr"]), false);
    assert.equal(canPickFlow("sdr", ["sdr", "ae"]), false);
    assert.equal(canPickFlow("ae", ["sdr", "ae"]), false);
    assert.equal(canPickFlow(null, undefined), false);
  });
  it("shows the viewing line only to general reps with a single flow", () => {
    assert.equal(viewingFlowKey(null, ["sdr"], "sdr"), "coachViewingCalls");
    assert.equal(viewingFlowKey("general", ["ae"], "ae"), "coachViewingMeetings");
    assert.equal(viewingFlowKey(null, ["sdr", "ae"], "sdr"), null);
    assert.equal(viewingFlowKey("ae", ["ae"], "ae"), null);
    assert.equal(ES.coachViewingCalls, "Estás viendo: llamadas");
  });
  it("passes the flow to the interactions query", () => {
    assert.equal(interactionsQuery({ stepId: "", state: "", meetingOnly: false }, "ae"), "limit=50&flow=ae");
  });
  it("picks the newest self report", () => {
    assert.equal(latestSelfReportId([]), null);
    assert.equal(latestSelfReportId(null), null);
    assert.equal(latestSelfReportId([{ report_id: "t", scope: "team", period_start: "2026-09-20" }]), null);
    assert.equal(
      latestSelfReportId([
        { report_id: "old", scope: "self", period_start: "2026-09-01" },
        { report_id: "new", scope: "self", period_start: "2026-09-22" },
        { report_id: "team", scope: "team", period_start: "2026-09-27" },
      ]),
      "new",
    );
  });
});

describe("rateOrCount", () => it("a rate needs three calls behind it; fewer show the count", () => {
  const p = ES as never;
  assert.equal(rateOrCount(p, 0, 0, null), "—");
  assert.equal(rateOrCount(p, 1, 2, 0.5), "1 de 2");
  assert.equal(rateOrCount(p, 2, 3, 2 / 3), "67 %");
}));
