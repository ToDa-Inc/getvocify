import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { bubblesForTurn } from "./transcript-bubbles.ts";

describe("bubblesForTurn", () => {
  it("keeps short replies as one bubble", () => {
    assert.deepEqual(bubblesForTurn("Abrazo, chicos. Abrazo."), ["Abrazo, chicos. Abrazo."]);
  });

  it("splits long turns only between sentences", () => {
    const text = "Perfecto, tío. Cuando lo vayamos probando os decimos, vale. Pues os paso esto y a por ello. ¿Qué tal?";
    const bubbles = bubblesForTurn(text, 60);
    assert.deepEqual(bubbles, [
      "Perfecto, tío. Cuando lo vayamos probando os decimos, vale.",
      "Pues os paso esto y a por ello. ¿Qué tal?",
    ]);
    assert.equal(bubbles.join(" "), text);
  });

  it("never cuts a single long sentence", () => {
    const long = "palabra ".repeat(60).trim();
    assert.deepEqual(bubblesForTurn(long, 40), [long]);
  });

  it("drops empty text", () => {
    assert.deepEqual(bubblesForTurn("   "), []);
  });
});
