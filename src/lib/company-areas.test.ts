import { describe, it, test } from "node:test";
import assert from "node:assert/strict";
import { areaFillScope, areasFromKnowledge, knowledgeFromAreas, withFunnelStages } from "./company-areas.ts";

describe("company areas", () => {
  it("shows what Vocify knows as six plain texts, lists as one line each", () => {
    const areas = areasFromKnowledge(
      { notes: "Somos Vocify.", pricing: "49 € al mes", icp: "Equipos de 5 a 50", competitors: [{ name: "Gong", how_to_talk: "más caro" }, { name: "Chorus" }], proofs: [{ customer: "Acme", change: "+30% reuniones" }] },
      "Ayuda en directo",
    );
    assert.deepEqual(areas, {
      company: "Somos Vocify.",
      product: "Ayuda en directo",
      offer: "49 € al mes",
      competition: "Gong — más caro\nChorus",
      icp: "Equipos de 5 a 50",
      cases: "Acme — +30% reuniones",
    });
    assert.deepEqual(areasFromKnowledge(null, null), { company: "", product: "", offer: "", competition: "", icp: "", cases: "" });
  });

  it("turns the six texts back into what Vocify keeps, without touching what the window does not show", () => {
    const before = { notes: "viejo", personas: [{ name: "CEO" }], bad_fit: "Autónomos" };
    const { knowledge, productContext } = knowledgeFromAreas(before, {
      company: " Somos Vocify. ",
      product: "Ayuda en directo",
      offer: "49 € al mes",
      competition: "Gong — más caro\n\nChorus: sin español\n",
      icp: "Equipos de 5 a 50",
      cases: "Acme - +30% reuniones",
    });
    assert.equal(productContext, "Ayuda en directo");
    assert.deepEqual(knowledge, {
      notes: "Somos Vocify.",
      personas: [{ name: "CEO" }],
      bad_fit: "Autónomos",
      pricing: "49 € al mes",
      icp: "Equipos de 5 a 50",
      competitors: [{ name: "Gong", how_to_talk: "más caro" }, { name: "Chorus", how_to_talk: "sin español" }],
      proofs: [{ customer: "Acme", change: "+30% reuniones" }],
    });
  });

  it("gives the first interaction of the funnel the first contact and the rest the deal, leaving other calls alone", () => {
    const list = withFunnelStages([
      { label: "Cold call", stage: "deal" as const },
      { label: "Discovery", stage: "first_contact" as const },
      { label: "Demo", stage: "first_contact" as const },
    ]);
    assert.deepEqual(list.map((item) => item.stage), ["first_contact", "deal", "deal"]);
  });
});

test("each area but the product is filled by Vocify into its own part of the notes", () => {
  assert.deepEqual(areaFillScope("company"), { texts: ["notes"] });
  assert.deepEqual(areaFillScope("offer"), { texts: ["pricing"] });
  assert.deepEqual(areaFillScope("icp"), { texts: ["icp"] });
  assert.deepEqual(areaFillScope("competition"), { list: "competitors" });
  assert.deepEqual(areaFillScope("cases"), { list: "proofs" });
  assert.equal(areaFillScope("product"), null);
});
