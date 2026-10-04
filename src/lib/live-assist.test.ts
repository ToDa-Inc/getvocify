import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { addCard, assistContext, askAfterMs, objectionCard, streamedDraft } from "./live-assist.ts";
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
  it("asks about their latest words with the conversation around them, as it is on screen", () => {
    const context = assistContext([
      turn("0", "rep", "Os enseño la demo."),
      turn("1", "prospect", "La verdad es que nos parece bastante caro para el equipo."),
      turn("2", "rep", "", "vale"),
    ]);
    assert.equal(context?.latestTurn, "La verdad es que nos parece bastante caro para el equipo.");
    assert.equal(context?.transcriptWindow, "You: Os enseño la demo.\nThem: La verdad es que nos parece bastante caro para el equipo.\nYou: vale");
  });

  it("waits until they said something substantial", () => {
    assert.equal(assistContext([turn("0", "prospect", "Sí, vale.")]), null);
    assert.equal(assistContext([turn("0", "rep", "Os cuento el precio ahora mismo.")]), null);
  });

  it("asks only about what they said since the last ask, so help answers the newest thing", () => {
    const first = "Nos parece caro para lo que necesitamos ahora mismo.";
    const said = `${first} Además ya estamos usando Gong y nos funciona bien.`;
    const context = assistContext([turn("1", "prospect", said)], { turnKey: "1", length: first.length });
    assert.equal(context?.latestTurn, "Además ya estamos usando Gong y nos funciona bien.");
  });

  it("reads the words still settling too, so a pause is enough to ask", () => {
    const context = assistContext([turn("1", "prospect", "Ya, pero la verdad", "es que nos parece bastante caro")]);
    assert.equal(context?.latestTurn, "Ya, pero la verdad es que nos parece bastante caro");
    assert.equal(context?.settled, false);
  });

  it("a few new words after the last ask are not worth asking about", () => {
    const first = "Nos parece caro para lo que necesitamos ahora mismo.";
    assert.equal(assistContext([turn("1", "prospect", `${first} Vale, sí.`)], { turnKey: "1", length: first.length }), null);
  });

  it("a new turn of theirs is asked about whole", () => {
    const context = assistContext([turn("2", "prospect", "Esto no lo decido yo, lo ve mi director financiero.")], { turnKey: "1", length: 40 });
    assert.equal(context?.settled, true);
    assert.equal(context?.latestTurn, "Esto no lo decido yo, lo ve mi director financiero.");
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
  const { coolingDown, cooldownKey, CATEGORY_COOLDOWN_MS } = await import("./live-assist.ts");
  const card = objectionCard(suggestion(), 1000)!;

  it("waits a minute before the same kind of help interrupts again", () => {
    const shown = { [cooldownKey(card)]: 1000 };
    assert.equal(coolingDown(card, shown, 1000 + CATEGORY_COOLDOWN_MS - 1), true);
    assert.equal(coolingDown(card, shown, 1000 + CATEGORY_COOLDOWN_MS), false);
    const other = objectionCard(suggestion({ objection_type: "timing", say_this: "¿Qué cambia en marzo?" }), 2000)!;
    assert.equal(coolingDown(other, shown, 2000), false);
  });

});

describe("bridge while the answer is written", async () => {
  const { bridgeLine, draftCard, draftType, spokenLanguage } = await import("./live-assist.ts");

  it("spots the objection type before the answer is finished", () => {
    assert.equal(draftType('{"is_objection": true, "objection_type": "pri'), null);
    assert.equal(draftType('{"is_objection": true, "objection_type": "price", "urg'), "price");
    assert.equal(draftType('{"is_objection": false, "objection_type": "none"'), null);
    assert.equal(draftType('{"is_objection": true, "objection_type": "made_up"'), null);
  });

  it("speaks the language they spoke", () => {
    assert.equal(spokenLanguage("Nos parece caro para el equipo"), "es");
    assert.equal(spokenLanguage("It's too expensive for the team right now"), "en");
    assert.equal(bridgeLine("price", "¿Y esto cuánto cuesta?"), "Es normal mirarlo con lupa…");
    assert.equal(bridgeLine("unknown_type", "that is not for us"), "I hear you…");
  });

  it("a draft carries only the label and the bridge", () => {
    const draft = draftCard("question", "¿Se conecta con HubSpot?", 5);
    assert.deepEqual([draft.stage, draft.kind, draft.label, draft.sayThis], ["draft", "question", "Question", ""]);
  });

  it("questions become their own kind of card", () => {
    const card = objectionCard(suggestion({ objection_type: "question", say_this: "Sí, con HubSpot y Pipedrive." }), 1)!;
    assert.deepEqual([card.kind, card.label, card.stage], ["question", "Question", "ready"]);
  });
});

describe("askAfterMs", () => {
  it("asks right after their sentence settles", () => {
    assert.equal(askAfterMs({ settled: true }), 300);
  });

  it("words still settling wait long enough to be a real pause, never a breath mid-sentence", () => {
    assert.equal(askAfterMs({ settled: false }), 2500);
  });
});

describe("streamedDraft", () => {
  it("a loading card as soon as the kind of objection is known", () => {
    const card = streamedDraft('{"is_objection": true, "objection_type": "trust", "say_this": "', "Me da miedo", 1);
    assert.equal(card?.label, "Trust");
    assert.equal(card?.stage, "draft");
  });

  it("never shows the answer's words before it is complete, so what the rep reads never changes", () => {
    const card = streamedDraft('{"is_objection": true, "objection_type": "price", "say_this": "Para ocho comerciales', "Es caro", 5);
    assert.equal(card?.sayThis, "");
  });

  it("offers a filler line to say at once while the answer is written, in their language", () => {
    const card = streamedDraft('{"is_objection": true, "objection_type": "price"', "La verdad es que es caro", 5);
    assert.equal(card?.bridge, "Es normal mirarlo con lupa…");
  });

  it("nothing until it knows it is an objection", () => {
    assert.equal(streamedDraft('{"is_objection": false', "Hola", 1), null);
  });
});
