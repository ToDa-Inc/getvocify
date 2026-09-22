import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { productCatalog } from "./product-catalog.ts";
import {
  activityLabel,
  adherenceBarRatio,
  objectionCategoriesEmptyMessage,
  objectionResolutionCountsText,
  repsByName,
  teamAdherenceHasData,
  teamInsightsView,
  visibleObjectionCategories,
  winsForFilter,
} from "./team-insights.ts";

const reps = [
  { userId: "b", name: "Carlos" },
  { userId: "a", name: "Ana" },
];

const metrics = {
  attempts: 4,
  connected: 2,
  meetings: 1,
  won: null as number | null,
  lost: null as number | null,
  unresolvedWins: 1,
  adherence: 0.2,
  met: 2,
  applicable: 10,
  coverageCrm: "unavailable" as const,
  sampleLimited: false,
};

const teamUiRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("team insights", () => {
  it("team metric blocks expose an accessible table", () => {
    for (const file of [
      "TeamOverview.tsx",
      "AdherenceBreakdown.tsx",
      "ObjectionBreakdown.tsx",
      "OutcomeBreakdown.tsx",
    ]) {
      const src = readFileSync(join(teamUiRoot, "features/team-insights/components", file), "utf8");
      assert.match(src, /<table>/);
    }
  });

  it("team dashboard sources omit leaderboard and scorecard widgets", () => {
    const page = readFileSync(join(teamUiRoot, "pages/dashboard/TeamInsightsPage.tsx"), "utf8");
    const features = readFileSync(
      join(teamUiRoot, "features/team-insights/components/TeamOverview.tsx"),
      "utf8",
    );
    assert.equal(/\bleaderboard\b/i.test(page + features), false);
    assert.equal(/scorecard/i.test(page + features), false);
  });

  it("labels missing activity as unavailable and real zero as zero", () => {
    assert.equal(activityLabel(null, productCatalog.ES.unavailable), "No disponible");
    assert.equal(activityLabel(null, productCatalog.EN.unavailable), "Not available");
    assert.equal(activityLabel(0, productCatalog.ES.unavailable), "0");
  });

  it("orders reps by name and keeps an unresolved win out of one person's count", () => {
    assert.deepEqual(repsByName(reps).map((rep) => rep.name), ["Ana", "Carlos"]);
    const deals = [
      { dealId: "deal-7", status: "won" as const, attribution: "unresolved" as const, ownerUserId: null },
      { dealId: "deal-8", status: "won" as const, attribution: "assigned" as const, ownerUserId: "a" },
    ];
    assert.equal(winsForFilter(deals, "a").length, 1);
    assert.equal(winsForFilter(deals, null).length, 2);
  });

  it("labels stable keys through the catalog and keeps legacy Spanish names", () => {
    const es = productCatalog.ES;
    const en = productCatalog.EN;
    assert.equal(objectionCategoriesEmptyMessage([], es.objections, es.teamObjectionsEmptyWeek), es.teamObjectionsEmptyWeek);
    assert.equal(
      objectionCategoriesEmptyMessage([{ name: "Precio", count: 0, resolved: 0, open: 0, unknown: 0 }], es.objections, es.teamObjectionsEmptyWeek),
      es.teamObjectionsEmptyWeek,
    );
    assert.equal(objectionCategoriesEmptyMessage([{ name: "price", count: 2, resolved: 1, open: 1, unknown: 0 }], es.objections, es.teamObjectionsEmptyWeek), null);
    assert.equal(objectionCategoriesEmptyMessage([{ name: "Precio", count: 1, resolved: 0, open: 0, unknown: 1 }], es.objections, es.teamObjectionsEmptyWeek), null);
    assert.equal(
      objectionCategoriesEmptyMessage([], en.objections, en.teamObjectionsEmptyWeek),
      en.teamObjectionsEmptyWeek,
    );
    assert.deepEqual(visibleObjectionCategories([
      { name: "timing", count: 2, resolved: 0, open: 1, unknown: 1 },
      { name: "price", count: 5, resolved: 2, open: 2, unknown: 1 },
      { name: "Plazo", count: 2, resolved: 0, open: 1, unknown: 1 },
      { name: "authority", count: 0, resolved: 0, open: 0, unknown: 0 },
    ], es.objections), [
      { name: "Precio", count: 5, resolved: 2, open: 2, unknown: 1 },
      { name: "Plazo", count: 2, resolved: 0, open: 1, unknown: 1 },
      { name: "Plazo", count: 2, resolved: 0, open: 1, unknown: 1 },
    ]);
    assert.deepEqual(visibleObjectionCategories([
      { name: "price", count: 2, resolved: 1, open: 0, unknown: 1 },
      { name: "timing", count: 2, resolved: 0, open: 2, unknown: 0 },
      { name: "trust", count: 3, resolved: 1, open: 1, unknown: 1 },
    ], en.objections), [
      { name: "Trust", count: 3, resolved: 1, open: 1, unknown: 1 },
      { name: "Price", count: 2, resolved: 1, open: 0, unknown: 1 },
      { name: "Timing", count: 2, resolved: 0, open: 2, unknown: 0 },
    ]);
    assert.equal(
      objectionResolutionCountsText({ resolved: 1, open: 2, unknown: 0 }, es),
      `${es.resolutionResolved} 1 ${es.resolutionOpen} 2 ${es.resolutionUnknown} 0`,
    );
  });

  it("shows an adherence bar only when adherence and applicable steps exist", () => {
    assert.equal(adherenceBarRatio({ adherence: null, met: 0, applicable: 10 }), null);
    assert.equal(adherenceBarRatio({ adherence: 0.2, met: 2, applicable: 0 }), null);
    assert.equal(adherenceBarRatio({ adherence: 0.2, met: 2, applicable: 10 }), 0.2);
  });

  it("detects an empty scoped adherence payload", () => {
    assert.equal(teamAdherenceHasData({ attempts: 0, met_steps: 0, objection_categories: [] }), false);
    assert.equal(teamAdherenceHasData({ attempts: 1, met_steps: 0 }), true);
  });

  it("sample limited keeps win rate inconclusive", () => {
    const es = productCatalog.ES;
    const view = teamInsightsView({
      role: "admin",
      companyEmpty: false,
      filters: { period: "week", motion: null, userId: null },
      reps,
      metrics: {
        ...metrics,
        coverageCrm: "complete",
        won: 3,
        lost: 1,
        sampleLimited: true,
      },
      copy: es,
    });
    assert.equal(view.kind, "ready");
    assert.equal(view.winRate, null);
  });

  it("new company onboarding is distinct from zero performance", () => {
    const es = productCatalog.ES;
    const view = teamInsightsView({
      role: "admin",
      companyEmpty: true,
      filters: { period: "week", motion: null, userId: null },
      reps,
      metrics: null,
      copy: es,
    });
    assert.equal(view.kind, "new");
    assert.equal(view.title, es.teamNewPanel);
    assert.equal(view.metrics, null);
  });

  it("does not turn an empty filter or a missing close into a zero rate", () => {
    const es = productCatalog.ES;
    const en = productCatalog.EN;
    const empty = teamInsightsView({
      role: "admin",
      companyEmpty: false,
      filters: { period: "week", motion: null, userId: "a" },
      reps,
      metrics: null,
      copy: es,
    });
    assert.equal(empty.kind, "empty");
    assert.equal(empty.title, es.teamNoDataForFilters);
    const partial = teamInsightsView({
      role: "owner",
      companyEmpty: false,
      filters: { period: "week", motion: null, userId: null },
      reps,
      metrics,
      copy: es,
    });
    assert.equal(partial.kind, "ready");
    assert.equal(partial.winRate, null);
    assert.equal(partial.partialCrmWarning, true);
    assert.equal(partial.metrics?.meetings, 1);
    assert.equal(partial.metrics?.won, null);
    const member = teamInsightsView({
      role: "member",
      companyEmpty: false,
      filters: { period: "week", motion: null, userId: null },
      reps,
      metrics,
      copy: es,
    });
    assert.equal(member.kind, "denied");
    assert.equal(member.title, es.teamDenied);
    assert.equal(member.metrics, null);
    const deniedEn = teamInsightsView({
      role: "member",
      companyEmpty: false,
      filters: { period: "week", motion: null, userId: null },
      reps,
      metrics,
      copy: en,
    });
    assert.equal(deniedEn.title, en.teamDenied);
  });
});
