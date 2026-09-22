import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  activityLabel,
  adherenceBarRatio,
  objectionCategoriesEmptyMessage,
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
};

describe("team insights", () => {
  it("labels missing activity as unavailable and real zero as zero", () => {
    assert.equal(activityLabel(null), "No disponible");
    assert.equal(activityLabel(0), "0");
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

  it("shows the Madrid-week empty copy and Spanish category names only", () => {
    assert.equal(objectionCategoriesEmptyMessage([]), "No hay objeciones esta semana.");
    assert.equal(objectionCategoriesEmptyMessage([{ name: "Precio", count: 0 }]), "No hay objeciones esta semana.");
    assert.equal(objectionCategoriesEmptyMessage([{ name: "price", count: 2 }]), "No hay objeciones esta semana.");
    assert.equal(objectionCategoriesEmptyMessage([{ name: "Precio", count: 1 }]), null);
    assert.deepEqual(visibleObjectionCategories([
      { name: "Plazo", count: 2 },
      { name: "Precio", count: 1 },
      { name: "price", count: 5 },
      { name: "Autoridad", count: 0 },
    ]), [
      { name: "Plazo", count: 2 },
      { name: "Precio", count: 1 },
    ]);
    assert.deepEqual(visibleObjectionCategories([
      { name: "Precio", count: 2 },
      { name: "Plazo", count: 2 },
      { name: "Confianza", count: 3 },
    ]), [
      { name: "Confianza", count: 3 },
      { name: "Plazo", count: 2 },
      { name: "Precio", count: 2 },
    ]);
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

  it("does not turn an empty filter or a missing close into a zero rate", () => {
    const empty = teamInsightsView({ role: "admin", companyEmpty: false, filters: { period: "week", motion: null, userId: "a" }, reps, metrics: null });
    assert.equal(empty.kind, "empty");
    assert.equal(empty.title, "No hay datos para estos filtros");
    const partial = teamInsightsView({ role: "owner", companyEmpty: false, filters: { period: "week", motion: null, userId: null }, reps, metrics });
    assert.equal(partial.kind, "ready");
    assert.equal(partial.winRate, null);
    assert.equal(partial.partialWarning, "Falta parte de los cierres del CRM");
    assert.equal(partial.metrics?.meetings, 1);
    assert.equal(partial.metrics?.won, null);
    const member = teamInsightsView({ role: "member", companyEmpty: false, filters: { period: "week", motion: null, userId: null }, reps, metrics });
    assert.equal(member.kind, "denied");
    assert.equal(member.metrics, null);
  });
});
