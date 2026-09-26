import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  trendBarRatio,
  trendCellText,
  trendHasConversations,
  trendRows,
  trendSampleLimited,
  trendWeekLabel,
  type TrendPayload,
  type TrendWeek,
} from "./team-adherence-trend.ts";

const copy = productCatalog.ES;

function week(overrides: Partial<TrendWeek> = {}): TrendWeek {
  return {
    week_start: "2026-09-21",
    state: "gap",
    interactions: 0,
    scored: 0,
    without_playbook: 0,
    without_score: 0,
    met_steps: 0,
    missed_steps: 0,
    applicable_steps: 0,
    unknown_steps: 0,
    not_applicable_steps: 0,
    adherence: null,
    coverage: null,
    sample_limited: false,
    playbook_version_ids: [],
    new_playbook_version: false,
    ...overrides,
  };
}

const scored = week({ state: "scored", interactions: 3, scored: 3, met_steps: 18, applicable_steps: 24, adherence: 0.75 });

describe("team adherence trend", () => {
  it("a gap has no bar and says there were no conversations, never 0 %", () => {
    assert.equal(trendBarRatio(week()), null);
    assert.equal(trendCellText(week(), copy), "Sin conversaciones");
  });

  it("a scored week shows met of scorable steps", () => {
    assert.equal(trendBarRatio(scored), 0.75);
    assert.equal(trendCellText(scored, copy), "18 de 24");
  });

  it("unscored conversations are said apart, by reason", () => {
    const noPlaybook = week({ state: "unscored", interactions: 3, without_playbook: 2, without_score: 1 });
    assert.equal(trendBarRatio(noPlaybook), null);
    assert.equal(trendCellText(noPlaybook, copy), "2 sin proceso · 1 sin puntuar");
    const mixed = { ...scored, interactions: 4, without_score: 1 };
    assert.equal(trendCellText(mixed, copy), "18 de 24 · 1 sin puntuar");
  });

  it("scored conversations with only unknown steps have no scorable steps", () => {
    const onlyUnknown = week({ state: "unscored", interactions: 1, scored: 1, unknown_steps: 3 });
    assert.equal(trendCellText(onlyUnknown, copy), "Sin pasos evaluables");
  });

  it("a playbook version change is named in the cell", () => {
    assert.equal(trendCellText({ ...scored, new_playbook_version: true }, copy), "18 de 24 · Proceso actualizado");
  });

  it("team first, then reps by name, never by adherence", () => {
    const payload: TrendPayload = {
      coverage: "complete",
      timezone: "Europe/Madrid",
      weeks: [{ week_start: "2026-09-21", week_end: "2026-09-27", in_progress: true }],
      team: { weeks: [scored] },
      reps: [
        { user_id: "c", name: "Carlos", weeks: [{ ...scored, adherence: 1 }] },
        { user_id: "a", name: "Ana", weeks: [{ ...scored, adherence: 0.1 }] },
      ],
    };
    assert.deepEqual(
      trendRows(payload, copy.teamTitle).map((row) => row.name),
      ["Equipo", "Ana", "Carlos"],
    );
    assert.deepEqual(
      trendRows({ ...payload, team: null }, copy.teamTitle).map((row) => row.key),
      ["a", "c"],
    );
  });

  it("detects conversations and small samples across rows", () => {
    const rows = [{ key: "a", name: "Ana", weeks: [week(), week()] }];
    assert.equal(trendHasConversations(rows), false);
    assert.equal(trendSampleLimited(rows), false);
    const withData = [{ key: "a", name: "Ana", weeks: [week(), { ...scored, sample_limited: true }] }];
    assert.equal(trendHasConversations(withData), true);
    assert.equal(trendSampleLimited(withData), true);
  });

  it("labels a week by its local Monday", () => {
    assert.equal(trendWeekLabel("2026-09-21", "es-ES"), "21 sept");
    assert.equal(trendWeekLabel("2026-08-03", "en-GB"), "3 Aug");
  });
});
