import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  blankItem,
  cleanKnowledge,
  isEmptyKnowledge,
  knowledgeSummary,
  sectionFilled,
  suggestedCompetitors,
  tabCount,
  tabFilled,
} from "./playbook-knowledge.ts";

const copy = {
  audience: "A quién vendemos",
  value: "Relato de valor",
  proofs: "{count} casos",
  proofOne: "1 caso",
  competitors: "{count} competidores",
  competitorOne: "1 competidor",
  triggers: "Señales de compra",
  pricing: "Precio",
};

describe("company knowledge", () => {
  it("knows which sections hold something", () => {
    const knowledge = { value_short: "Vocify rellena el CRM solo.", competitors: [{ name: "Aircall" }], proofs: [{ customer: " " }] };
    assert.equal(sectionFilled(knowledge, "value"), true);
    assert.equal(sectionFilled(knowledge, "proofs"), false);
    assert.equal(isEmptyKnowledge({}), true);
    assert.equal(isEmptyKnowledge({ personas: [{ name: "", cares_about: "" }] }), true);
    assert.equal(isEmptyKnowledge({ notes: "algo" }), false);
  });

  it("summarises the row in one line, singular-aware", () => {
    assert.equal(
      knowledgeSummary(
        { value_short: "x", proofs: [{ customer: "Acme" }, { customer: "Beta" }], competitors: [{ name: "Aircall" }] },
        copy,
      ),
      "Relato de valor · 2 casos · 1 competidor",
    );
    assert.equal(knowledgeSummary({}, copy), null);
    assert.equal(knowledgeSummary(null, copy), null);
  });

  it("cleans before saving: trims, drops unnamed items, empty keys and older extra fields, keeps paragraphs", () => {
    const clean = cleanKnowledge({
      value_long: "  Primero.\n\nDespués.  ",
      icp: "   ",
      differentiators: [" Sin formularios ", ""],
      competitors: [
        { name: " Aircall ", how_to_talk: "  pregunta qué pasa después de colgar ", landmines: "no decir caro" } as never,
        { name: "", how_to_talk: "x" },
      ],
      proofs: [{ customer: "Acme", change: " -40 % de tiempo en el CRM ", number: "40" } as never],
    });
    assert.deepEqual(clean, {
      value_long: "Primero.\n\nDespués.",
      differentiators: ["Sin formularios"],
      competitors: [{ name: "Aircall", how_to_talk: "pregunta qué pasa después de colgar" }],
      proofs: [{ customer: "Acme", change: "-40 % de tiempo en el CRM" }],
    });
    assert.deepEqual(blankItem("proofs"), { customer: "" });
  });
});

describe("company tabs and suggestions", () => {
  it("counts named stories and competitors and says which tabs hold something", () => {
    const knowledge = { pricing: "Por comercial", proofs: [{ customer: "Ríos" }, { customer: " " }], competitors: [] };
    assert.equal(tabCount(knowledge, "proofs"), 1);
    assert.equal(tabCount(knowledge, "competitors"), 0);
    assert.equal(tabCount(knowledge, "value"), null);
    assert.equal(tabFilled(knowledge, "value"), true);
    assert.equal(tabFilled(knowledge, "customer"), false);
  });

  it("suggests competitors the calls mention and the notes don't list, most mentioned first", () => {
    const mentions = [
      { name: "Modjo", count: 3 },
      { name: "Gong", count: 9 },
      { name: "HubSpot Calling", count: 7 },
      { name: " ", count: 4 },
    ];
    assert.deepEqual(
      suggestedCompetitors(mentions, new Set(["gong"])).map((mention) => mention.name),
      ["HubSpot Calling", "Modjo"],
    );
    assert.deepEqual(suggestedCompetitors(undefined, new Set()), []);
  });
});
