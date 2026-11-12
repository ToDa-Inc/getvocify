import { describe, it, test } from "node:test";
import assert from "node:assert/strict";
import { areaFillScope, areaItems, areasFromKnowledge, knowledgeFromAreas, withFunnelStages } from "./company-areas.ts";

describe("company areas", () => {
  it("shows what Vocify knows as plain texts, lists as one line each", () => {
    const areas = areasFromKnowledge(
      { notes: "Somos Vocify.", pricing: "49 € al mes", icp: "Equipos de 5 a 50", bad_fit: "Autónomos", personas: [{ name: "CEO", cares_about: "coste" }], triggers: [{ signal: "Vence su contrato", how_to_use: "Pide la fecha" }], competitors: [{ name: "Gong", how_to_talk: "más caro" }, { name: "Chorus" }], proofs: [{ customer: "Acme", change: "+30% reuniones" }] },
      "Ayuda en directo",
    );
    assert.deepEqual(areas, {
      company: "Somos Vocify.",
      product: "Ayuda en directo",
      offer: "49 € al mes",
      icp: "Equipos de 5 a 50",
      bad_fit: "Autónomos",
      personas: "CEO — coste",
      triggers: "Vence su contrato — Pide la fecha",
      competition: "Gong — más caro\nChorus",
      cases: "Acme — +30% reuniones",
    });
    assert.deepEqual(areasFromKnowledge(null, null), { company: "", product: "", offer: "", icp: "", bad_fit: "", personas: "", triggers: "", competition: "", cases: "" });
    assert.deepEqual(areaItems("CEO — coste\n\nCTO"), [{ title: "CEO", line: "coste" }, { title: "CTO", line: "" }]);
  });

  it("turns the texts back into what Vocify keeps, without touching what the window does not show", () => {
    const before = { notes: "viejo", value_short: "Valor", personas: [{ name: "CEO" }], bad_fit: "Autónomos" };
    const { knowledge, productContext } = knowledgeFromAreas(before, {
      company: " Somos Vocify. ",
      product: "Ayuda en directo",
      offer: "49 € al mes",
      competition: "Gong — más caro\n\nChorus: sin español\n",
      icp: "Equipos de 5 a 50",
      bad_fit: "",
      personas: "Gerente de ambulancias — tiempos de respuesta\nCEO",
      triggers: "",
      cases: "Acme - +30% reuniones",
    });
    assert.equal(productContext, "Ayuda en directo");
    assert.deepEqual(knowledge, {
      notes: "Somos Vocify.",
      value_short: "Valor",
      personas: [{ name: "Gerente de ambulancias", cares_about: "tiempos de respuesta" }, { name: "CEO" }],
      pricing: "49 € al mes",
      icp: "Equipos de 5 a 50",
      competitors: [{ name: "Gong", how_to_talk: "más caro" }, { name: "Chorus", how_to_talk: "sin español" }],
      proofs: [{ customer: "Acme", change: "+30% reuniones" }],
    });
  });

  it("with one area, writes only that one and leaves every other list as stored", () => {
    const before = { pricing: "viejo", personas: [{ name: "Gerente: flota", cares_about: "coste" }] };
    const areas = { ...areasFromKnowledge(before, ""), offer: "49 €" };
    const { knowledge } = knowledgeFromAreas(before, areas, "offer");
    assert.deepEqual(knowledge, { pricing: "49 €", personas: [{ name: "Gerente: flota", cares_about: "coste" }] });
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
  assert.deepEqual(areaFillScope("bad_fit"), { texts: ["bad_fit"] });
  assert.deepEqual(areaFillScope("personas"), { list: "personas" });
  assert.deepEqual(areaFillScope("triggers"), { list: "triggers" });
  assert.deepEqual(areaFillScope("competition"), { list: "competitors" });
  assert.deepEqual(areaFillScope("cases"), { list: "proofs" });
  assert.equal(areaFillScope("product"), null);
});
