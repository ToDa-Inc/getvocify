import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { COMPANY_AREAS, afterColon, companyAreaStates, homeProgress, nextStep, splitFunnel } from "./playbook-home.ts";

describe("playbook home helpers", () => {
  it("names the step each one leads to, and none after the last", () => {
    const steps = [{ label: "Cold call" }, { label: " Discovery " }, { label: "" }];
    assert.equal(nextStep(steps, 0), "Discovery");
    assert.equal(nextStep(steps, 1), "");
    assert.equal(nextStep(steps, 2), null);
  });

  it("puts a goal after a colon in lower case, but leaves an acronym as written", () => {
    assert.equal(afterColon(" Crear interés y acordar una reunión"), "crear interés y acordar una reunión");
    assert.equal(afterColon("ICP validado"), "ICP validado");
    assert.equal(afterColon("A"), "A");
  });

  it("keeps the calls outside the funnel apart and the order of each list", () => {
    const types = [
      { key: "a", stage: "first_contact" },
      { key: "sac", stage: "other" },
      { key: "b", stage: "deal" },
      { key: "tech", stage: "other" },
    ];
    const { funnel, other } = splitFunnel(types);
    assert.deepEqual(funnel.map((t) => t.key), ["a", "b"]);
    assert.deepEqual(other.map((t) => t.key), ["sac", "tech"]);
  });

  it("counts how many types already have something written", () => {
    assert.deepEqual(homeProgress([{ state: "live" }, { state: "empty" }, { state: "changes" }]), { total: 3, written: 2 });
    assert.deepEqual(homeProgress([]), { total: 0, written: 0 });
  });

  it("names the six areas of the company in the order they are shown, each opening a place in the company window", () => {
    assert.deepEqual(COMPANY_AREAS.map((area) => area.id), ["company", "product", "offer", "competition", "icp", "cases"]);
    assert.equal(COMPANY_AREAS.find((area) => area.id === "offer")?.opens, "offer");
    assert.equal(COMPANY_AREAS.find((area) => area.id === "icp")?.opens, "customer");
    assert.equal(COMPANY_AREAS.find((area) => area.id === "cases")?.opens, "proofs");
  });

  it("says which areas of the company already have something, as the company window shows them", () => {
    const none = companyAreaStates(null, "");
    assert.deepEqual(none.map((a) => a.filled), [false, false, false, false, false, false]);
    const some = companyAreaStates({ icp: "Tiendas de barrio", proofs: [{ customer: "Acme" }], notes: "" } as never, "  Vendemos un CRM  ");
    const by = Object.fromEntries(some.map((a) => [a.id, a.filled]));
    assert.deepEqual(by, { company: false, product: true, offer: false, competition: false, icp: true, cases: true });
  });
});
