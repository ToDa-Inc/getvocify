import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  bellActivityText,
  bellCount,
  nullableMetricLabel,
  reportAdherenceTrend,
  reportPagePresentation,
  reportSurface,
  reportTitleKey,
  snapshotMetricCells,
} from "./report-snapshot.ts";

describe("report adherence trend", () => {
  const cell = (state: string, met = 0, applicable = 0, sample_limited = false) => ({ state, met, applicable, sample_limited });
  const copy = {
    team: productCatalog.ES.teamTitle,
    unscored: productCatalog.ES.reportTrendUnscored,
    stepsTemplate: productCatalog.ES.teamAdherenceOf,
  };

  it("shows the same cells as the team email, team first", () => {
    const view = reportAdherenceTrend(
      {
        metrics: { attempts: 1, connected_calls: 1, meetings_agreed: 0, deals_won: null, adherence: null },
        coverage: { crm_outcomes: "unavailable" },
        coaching: null,
        adherence_trend: {
          weeks: ["2026-09-14", "2026-09-21"],
          team: [cell("unscored"), cell("scored", 9, 12)],
          reps: [{ name: "Ana", weeks: [cell("gap"), cell("scored", 4, 5, true)] }],
        },
      },
      copy,
    );
    assert.deepEqual(view?.weeks, ["2026-09-14", "2026-09-21"]);
    assert.deepEqual(view?.rows, [
      { name: copy.team, cells: ["Sin puntuar", "9 de 12"] },
      { name: "Ana", cells: ["—", "4 de 5*"] },
    ]);
    assert.equal(view?.sampleLimited, true);
  });

  it("is absent without a trend in the snapshot", () => {
    const view = reportAdherenceTrend(
      {
        metrics: { attempts: 1, connected_calls: 1, meetings_agreed: 0, deals_won: null, adherence: null },
        coverage: { crm_outcomes: "unavailable" },
        coaching: null,
      },
      copy,
    );
    assert.equal(view, null);
  });
});

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
    assert.deepEqual(surface.exampleLinks, []);
  });

  it("links example memos without inventing coaching on an empty period", () => {
    const unavailable = productCatalog.ES.unavailable;
    const surface = reportSurface(
      {
        metrics: { attempts: 0, connected_calls: 0, meetings_agreed: 0, deals_won: null, adherence: null },
        coverage: { crm_outcomes: "unavailable" },
        coaching: null,
        examples: ["memo-a"],
      },
      unavailable,
    );
    assert.deepEqual(surface.exampleLinks, ["/dashboard/memos/memo-a"]);
    assert.equal(surface.coaching, null);
  });

  it("hides the bell when nothing is unread and when the count is unknown", () => {
    assert.equal(bellCount(0), null);
    assert.equal(bellCount(null), null);
    assert.equal(bellCount(2), "2");
  });

  it("maps the persisted snapshot to page rows without recomputing metrics", () => {
    const snapshot = {
      metrics: { attempts: 8, connected_calls: 5, meetings_agreed: 2, deals_won: null, adherence: null },
      coverage: { crm_outcomes: "unavailable" },
      coaching: null,
    };
    const unavailable = productCatalog.ES.unavailable;
    const cells = snapshotMetricCells(snapshot, unavailable);
    const daily = reportPagePresentation(snapshot, { unavailable });
    assert.deepEqual(daily.days, []);
    assert.equal(daily.objections, null);
    assert.deepEqual(
      daily.rows.map((row) => row.value),
      [cells.attempts, cells.connected_calls, cells.meetings_agreed, cells.deals_won, cells.adherence],
    );
    assert.equal(daily.rows[3].value, productCatalog.ES.unavailable);
    assert.equal(
      snapshotMetricCells(snapshot, productCatalog.EN.unavailable).deals_won,
      productCatalog.EN.unavailable,
    );
  });

  it("shows a weekly day not yet observed as a gap, never as a zero bar", () => {
    const view = reportPagePresentation(
      {
        metrics: { attempts: 3, connected_calls: 2, meetings_agreed: 1, deals_won: null, adherence: null },
        coverage: { crm_outcomes: "unavailable" },
        coaching: null,
        report_type: "weekly",
        series: [
          { date: "2026-09-21", connected_calls: 2, meetings_agreed: 1, covered: true },
          { date: "2026-09-22", connected_calls: 0, meetings_agreed: 0, covered: true },
          { date: "2026-09-25", connected_calls: null, meetings_agreed: null, covered: false },
        ],
        objections: [{ name: "price", count: 2 }],
      },
      { unavailable: productCatalog.ES.unavailable },
    );
    assert.deepEqual(view.days.map((day) => day.connected), [2, 0, null]);
    assert.deepEqual(view.days.map((day) => day.covered), [true, true, false]);
    assert.deepEqual(view.objections, [{ name: "price", count: 2 }]);
  });

  it("reads team adherence as steps met, like the email", () => {
    const snapshot = {
      metrics: { attempts: 5, connected_calls: 4, meetings_agreed: 1, deals_won: null, adherence: 0.75 },
      coverage: { crm_outcomes: "unavailable" },
      coaching: null,
      scope: "team" as const,
      adherence_steps: { met: 18, applicable: 24 },
    };
    const cells = snapshotMetricCells(snapshot, productCatalog.ES.unavailable, productCatalog.ES.reportAdherenceSteps);
    assert.equal(cells.adherence, "18 de 24 pasos");
    const noPlaybook = snapshotMetricCells(
      { ...snapshot, metrics: { ...snapshot.metrics, adherence: null }, adherence_steps: null },
      productCatalog.ES.unavailable,
      productCatalog.ES.reportAdherenceSteps,
    );
    assert.equal(noPlaybook.adherence, "No disponible");
  });

  it("titles each report by what it covers", () => {
    assert.equal(reportTitleKey({ report_type: "daily", scope: "self" }), "reportTitleDaily");
    assert.equal(reportTitleKey({ report_type: "weekly", scope: "self" }), "reportTitleWeekly");
    assert.equal(reportTitleKey({ report_type: "weekly", scope: "team" }), "reportTitleTeam");
  });

  it("says what Vocify did and why, in the reader's language", () => {
    const es = productCatalog.ES;
    const crm = bellActivityText(
      { kind: "crm_updated", memo_id: "m-1", subject: "Ana Pérez", resources: ["deal", "contact", "task"], at: "x" },
      es,
    );
    assert.equal(crm.title, "CRM actualizado: deal, contacto y tareas");
    assert.equal(crm.why, "Por tu conversación con Ana Pérez");
    assert.equal(crm.href, "/dashboard/memos/m-1");
    const stage = bellActivityText(
      { kind: "meeting_stage", memo_id: "m-2", subject: null, resources: [], at: "x" },
      es,
    );
    assert.equal(stage.title, "Deal movido a la etapa de reunión agendada");
    assert.equal(stage.why, "Por una de tus conversaciones");
    const en = bellActivityText(
      { kind: "crm_updated", memo_id: "m-1", subject: "Ana", resources: ["note"], at: "x" },
      productCatalog.EN,
    );
    assert.equal(en.title, "CRM updated: note");
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
