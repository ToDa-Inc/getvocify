import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import { causeLabel, cellValue, goalsMarked, heatTone, lossesLine, worksHasVerdict, type TeamCoaching } from "./team-coaching.ts";

const ES = productCatalog.ES;
const EN = productCatalog.EN;

const side = (calls: number, goals: number) => ({ calls, goals, rate: calls ? goals / calls : null });

describe("heat map cells", () => {
  it("colours by rate only with three calls behind it, and never shows a % of one call", () => {
    assert.equal(heatTone({ applicable: 0, rate: null }), "none");
    assert.equal(heatTone({ applicable: 2, rate: 1 }), "few");
    assert.equal(heatTone({ applicable: 5, rate: 0.8 }), "high");
    assert.equal(heatTone({ applicable: 5, rate: 0.6 }), "mid");
    assert.equal(heatTone({ applicable: 5, rate: 0.2 }), "low");
    assert.equal(cellValue({ done: 0, applicable: 0, rate: null }), "—");
    assert.equal(cellValue({ done: 1, applicable: 2, rate: 0.5 }), "1/2");
    assert.equal(cellValue({ done: 5, applicable: 6, rate: 5 / 6 }), "83 %");
  });
});

describe("does the playbook work", () => {
  it("says nothing but 'not enough' until a comparison has a verdict", () => {
    const thin: TeamCoaching["works"] = {
      process: { with: side(2, 0), without: side(14, 0), verdict: "few_data" },
      steps: [{ step_id: "s", label: "S", with: side(9, 0), without: side(7, 0), verdict: "few_data" }],
    };
    assert.equal(worksHasVerdict(thin), false);
    assert.equal(goalsMarked(thin), 0);
    const ready = { ...thin, steps: [{ ...thin.steps[0], verdict: "helps" as const }] };
    assert.equal(worksHasVerdict(ready), true);
  });
});

describe("why we lose", () => {
  it("names every cause in both languages", () => {
    assert.equal(causeLabel(ES, { cause: "price", label: null }), ES.playbookObjectionCategories.price);
    assert.equal(causeLabel(ES, { cause: "custom:pide_descuento", label: "Pide descuento" }), "Pide descuento");
    assert.equal(causeLabel(ES, { cause: "obstacle:wrong_person", label: null }), "No era la persona");
    assert.equal(causeLabel(EN, { cause: "obstacle:unheard_of", label: null }), EN.teamCauseObstacles.other);
    assert.equal(causeLabel(ES, { cause: "no_conversation", label: null }), "Nunca se llegó a hablar");
    assert.equal(causeLabel(ES, { cause: "unclear", label: null }), "Sin causa clara en la llamada");
  });

  it("counts the sources without the zeros", () => {
    const losses = { total: 3, by_source: { not_interested: 2, disqualified: 0, crm_lost: 1 }, causes: [] };
    assert.equal(lossesLine(ES, losses), "3 perdidas · 2 no interesado · 1 perdidas en el CRM");
  });

  it("has every Equipo key in both languages", () => {
    const keys = Object.keys(EN).filter((key) => key.startsWith("team") && key !== "teamCauseObstacles");
    for (const key of keys) assert.ok(key in ES, `ES missing ${key}`);
    assert.deepEqual(Object.keys(ES.teamCauseObstacles).sort(), Object.keys(EN.teamCauseObstacles).sort());
  });
});
