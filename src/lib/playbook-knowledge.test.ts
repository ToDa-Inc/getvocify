import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  blankItem,
  cleanKnowledge,
  isEmptyKnowledge,
  knowledgeSummary,
  sectionFilled,
  visibleSections,
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
  it("shows only sections with content, plus the ones added by hand", () => {
    const knowledge = { value_short: "Vocify rellena el CRM solo.", competitors: [{ name: "Aircall" }], proofs: [{ customer: " " }] };
    assert.deepEqual(visibleSections(knowledge), ["value", "competitors"]);
    assert.deepEqual(visibleSections(knowledge, ["pricing"]), ["value", "competitors", "pricing"]);
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

  it("cleans before saving: trims, drops unnamed items and empty keys, keeps paragraphs", () => {
    const clean = cleanKnowledge({
      value_long: "  Primero.\n\nDespués.  ",
      icp: "   ",
      differentiators: [" Sin formularios ", ""],
      competitors: [{ name: " Aircall ", win_when: "  cuando quieren el CRM al día " }, { name: "", how_to_talk: "x" }],
      proofs: [{ customer: "Acme", tags: [" SaaS ", ""] }],
    });
    assert.deepEqual(clean, {
      value_long: "Primero.\n\nDespués.",
      differentiators: ["Sin formularios"],
      competitors: [{ name: "Aircall", win_when: "cuando quieren el CRM al día" }],
      proofs: [{ customer: "Acme", tags: ["SaaS"] }],
    });
    assert.deepEqual(blankItem("proofs"), { customer: "" });
  });
});
