import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { addCard, assistContext, objectionCard } from "./live-assist.ts";
import type { MeetingDisplayTurn } from "./meeting-transcript.ts";

const turn = (key: string, speaker: "rep" | "prospect", text: string, pending = ""): MeetingDisplayTurn => ({
  key,
  speaker,
  label: speaker === "rep" ? "You" : "Them",
  text,
  pending,
});

const suggestion = (overrides = {}) => ({
  is_objection: true,
  objection_type: "price",
  urgency: "high",
  say_this: "¿Comparado con qué os parece caro?",
  why_it_works: "Ancla el valor antes de negociar.",
  next_question: "¿Qué os cuesta hoy hacerlo a mano?",
  dont_say: "No bajes el precio todavía.",
  ...overrides,
});

describe("assistContext", () => {
  it("asks about their latest settled words with the conversation around them", () => {
    const context = assistContext([
      turn("0", "rep", "Os enseño la demo."),
      turn("1", "prospect", "La verdad es que nos parece bastante caro para el equipo."),
      turn("2", "rep", "", "vale"),
    ]);
    assert.equal(context?.latestTurn, "La verdad es que nos parece bastante caro para el equipo.");
    assert.equal(context?.transcriptWindow, "You: Os enseño la demo.\nThem: La verdad es que nos parece bastante caro para el equipo.");
  });

  it("waits until they said something substantial", () => {
    assert.equal(assistContext([turn("0", "prospect", "Sí, vale.")]), null);
    assert.equal(assistContext([turn("0", "rep", "Os cuento el precio ahora mismo.")]), null);
  });

  it("changes key only when their words change", () => {
    const a = assistContext([turn("1", "prospect", "Nos parece caro para ahora mismo.")]);
    const b = assistContext([turn("1", "prospect", "Nos parece caro para ahora mismo."), turn("2", "rep", "Entiendo.")]);
    const c = assistContext([turn("1", "prospect", "Nos parece caro para ahora mismo. Y lo decide Jorge.")]);
    assert.equal(a?.key, b?.key);
    assert.notEqual(a?.key, c?.key);
  });
});

describe("objectionCard", () => {
  it("turns a real objection into a card", () => {
    const card = objectionCard(suggestion(), 1);
    assert.equal(card?.label, "Price");
    assert.equal(card?.sayThis, "¿Comparado con qué os parece caro?");
    assert.equal(card?.thenAsk, "¿Qué os cuesta hoy hacerlo a mano?");
  });

  it("shows nothing when there is no objection or nothing to say", () => {
    assert.equal(objectionCard(suggestion({ is_objection: false }), 1), null);
    assert.equal(objectionCard(suggestion({ say_this: "  " }), 1), null);
    assert.equal(objectionCard(null, 1), null);
  });
});

describe("addCard", () => {
  it("keeps newest first, skips repeats and caps history", () => {
    const first = objectionCard(suggestion(), 1)!;
    const again = objectionCard(suggestion(), 2)!;
    const other = objectionCard(suggestion({ say_this: "¿Quién más decide?" , objection_type: "authority" }), 3)!;
    assert.deepEqual(addCard([first], again), [first]);
    assert.deepEqual(addCard([first], other).map((c) => c.label), ["Decision maker", "Price"]);
    assert.equal(addCard([first, first, first, first, first], other, 5).length, 5);
  });
});

describe("display rules", async () => {
  const { cardVisible, coolingDown, cooldownKey, repActivityKey, CARD_MIN_MS, CARD_MAX_MS, CATEGORY_COOLDOWN_MS } = await import("./live-assist.ts");
  const card = objectionCard(suggestion(), 1000)!;

  it("stays at least 4s even if the rep talks, and never more than 10s", () => {
    assert.equal(cardVisible(card, 1000 + CARD_MIN_MS - 1, 1500), true);
    assert.equal(cardVisible(card, 1000 + CARD_MIN_MS, 1500), false);
    assert.equal(cardVisible(card, 1000 + CARD_MAX_MS - 1, null), true);
    assert.equal(cardVisible(card, 1000 + CARD_MAX_MS, null), false);
  });

  it("ignores rep speech from before the card appeared", () => {
    assert.equal(cardVisible(card, 1000 + CARD_MIN_MS + 1, 900), true);
  });

  it("waits a minute before the same kind of help interrupts again", () => {
    const shown = { [cooldownKey(card)]: 1000 };
    assert.equal(coolingDown(card, shown, 1000 + CATEGORY_COOLDOWN_MS - 1), true);
    assert.equal(coolingDown(card, shown, 1000 + CATEGORY_COOLDOWN_MS), false);
    const other = objectionCard(suggestion({ objection_type: "timing", say_this: "¿Qué cambia en marzo?" }), 2000)!;
    assert.equal(coolingDown(other, shown, 2000), false);
  });

  it("notices when the rep says something new", () => {
    const a = repActivityKey([turn("0", "rep", "Hola"), turn("1", "prospect", "Es caro")]);
    const b = repActivityKey([turn("0", "rep", "Hola"), turn("1", "prospect", "Es caro"), turn("2", "rep", "", "Entiendo")]);
    assert.notEqual(a, b);
  });
});
