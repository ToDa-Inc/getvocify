import assert from "node:assert/strict";
import { test } from "node:test";
import { plainAnswer, plainSummary } from "./summary-line.ts";

test("drops headings, bullets and emphasis from a markdown summary", () => {
  const summary = "### Interrupción por reunión\n* Roberto pidió **retomar** la llamada.\n\n### Contacto\n- Mañana.";
  assert.equal(plainSummary(summary), "Roberto pidió retomar la llamada. Mañana.");
});

test("plain text and empty values pass through", () => {
  assert.equal(plainSummary("Hablaron del almacén."), "Hablaron del almacén.");
  assert.equal(plainSummary(undefined), "");
});

test("an answer keeps its lines but loses emphasis and headings", () => {
  const answer = "Quedó una **reunión de demostración**.\n\n### Contexto\n- **Equipo:** 3 comerciales.\n* Usan HubSpot.";
  assert.equal(plainAnswer(answer), "Quedó una reunión de demostración.\n\nContexto\n· Equipo: 3 comerciales.\n· Usan HubSpot.");
});
