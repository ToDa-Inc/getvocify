import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  answerCard,
  assistContext,
  CARD_COOLDOWN_MS,
  checkTiming,
  cooldownLeft,
  repReplied,
  skipAnswered,
  bridgeLine,
  draftCard,
  nextStep,
  objectionCard,
  previousAnswers,
  PAUSE_MS,
  prospectSilent,
  streamedDraft,
  turnCheck,
} from "./live-assist.ts";
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
  });

  it("shows nothing when there is no objection or nothing to say", () => {
    assert.equal(objectionCard(suggestion({ is_objection: false }), 1), null);
    assert.equal(objectionCard(suggestion({ say_this: "  " }), 1), null);
    assert.equal(objectionCard(null, 1), null);
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

describe("turnCheck", () => {
  it("checks the moment their audio goes quiet, and lets the classifier say if they are done", () => {
    assert.deepEqual(turnCheck({ settled: false, paused: true }), { afterMs: 0, final: false });
  });

  it("while they still talk, waits for a real pause in their words, then takes the turn as over", () => {
    assert.deepEqual(turnCheck({ settled: true, paused: false }), { afterMs: 2500, final: true });
  });

  it("with no audio to read, a settled sentence is checked at once and words still settling after a pause", () => {
    assert.deepEqual(turnCheck({ settled: true, paused: null }), { afterMs: 300, final: true });
    assert.deepEqual(turnCheck({ settled: false, paused: null }), { afterMs: 2500, final: true });
  });
});

describe("bridgeLine", () => {
  it("a question's filler promises nothing: the answer may be \"I'll confirm it\"", () => {
    assert.equal(bridgeLine("question", "¿Y esto funciona también desde el móvil?"), "Mira…");
    assert.equal(bridgeLine("question", "Does this work from a phone?"), "Right, so…");
  });
});

describe("PAUSE_MS", () => {
  it("their side quiet for 0.3 s is enough to check: the classifier guards a mid-sentence breath", () => {
    assert.equal(PAUSE_MS, 300);
  });
});

describe("prospectSilent", () => {
  it("their side is silent below speech level, never on a quiet word", () => {
    assert.equal(prospectSilent(0), true);
    assert.equal(prospectSilent(0.1), true);
    assert.equal(prospectSilent(0.4), false);
  });
});

describe("nextStep with the playbook's own objections", () => {
  it("a custom match answers with the entry and its name", () => {
    const reading = { finished: true, objection: "custom", entry_id: "objection:custom:x", label: "Venta muy diferente" };
    assert.deepEqual(nextStep(reading, false), {
      do: "answer",
      type: "custom",
      entryId: "objection:custom:x",
      label: "Venta muy diferente",
    });
  });

  it("the card carries the entry's name instead of a generic label", () => {
    assert.equal(draftCard("custom", "Damos pocas visitas", 1, "Venta muy diferente").label, "Venta muy diferente");
    assert.equal(draftCard("price", "caro", 1).label, "Price");
  });

  it("a custom reading without its entry is skipped, never a card with nothing to follow", () => {
    assert.deepEqual(nextStep({ finished: true, objection: "custom" }, false), { do: "skip" });
  });
});

describe("nextStep", () => {
  it("a finished objection shows its card at once and has the answer written for it", () => {
    assert.deepEqual(nextStep({ finished: true, objection: "price" }, false), { do: "answer", type: "price" });
  });

  it("a thought still going waits for more, unless they have been quiet long enough", () => {
    assert.deepEqual(nextStep({ finished: false, objection: "none" }, false), { do: "wait" });
    assert.deepEqual(nextStep({ finished: false, objection: "trust" }, true), { do: "answer", type: "trust" });
  });

  it("no objection asks no model at all", () => {
    assert.deepEqual(nextStep({ finished: true, objection: "none" }, false), { do: "skip" });
    assert.deepEqual(nextStep({ finished: true, objection: "weather" }, false), { do: "skip" });
  });

  it("no classifier falls back to asking the answer model directly", () => {
    assert.deepEqual(nextStep(null, false), { do: "ask" });
    assert.deepEqual(nextStep({ finished: null, objection: null }, true), { do: "ask" });
  });
});

describe("answerCard", () => {
  it("the answer lands in the card already on screen: same place, label, filler line and clock", () => {
    const draft = draftCard("price", "me parece bastante caro", 100);
    const answer = objectionCard(suggestion({ objection_type: "trust" }), 900, "me parece bastante caro")!;
    const shown = answerCard(draft, answer);
    assert.equal(shown.id, draft.id);
    assert.equal(shown.at, 100);
    assert.equal(shown.label, "Price");
    assert.equal(shown.bridge, draft.bridge);
    assert.equal(shown.stage, "ready");
    assert.equal(shown.sayThis, "¿Comparado con qué os parece caro?");
  });

  it("no answer (failed, silent or too slow) never takes the card away: the filler stays, the dots stop", () => {
    const draft = draftCard("trust", "me da miedo que la IA escriba mal", 100);
    const shown = answerCard(draft, null)!;
    assert.equal(shown.id, draft.id);
    assert.equal(shown.label, "Trust");
    assert.equal(shown.bridge, draft.bridge);
    assert.equal(shown.stage, "ready");
    assert.equal(shown.sayThis, "");
    assert.equal(answerCard(null, null), null);
  });

  it("the card is the label, the filler line and one line: nothing else to read", () => {
    const card = objectionCard(suggestion(), 900, "me parece caro")!;
    assert.deepEqual(Object.keys(card).sort(), ["at", "bridge", "id", "kind", "label", "sayThis", "source", "stage"]);
  });

  it("with no card on screen yet, the answer shows as it came", () => {
    const answer = objectionCard(suggestion(), 900)!;
    assert.deepEqual(answerCard(null, answer), answer);
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

describe("transcript window", async () => {
  const { windowOf } = await import("./live-assist.ts");
  const line = (n: number) => `Them: ${String(n).padStart(4, "0")} ${"x".repeat(93)}`;
  const call = (count: number) => Array.from({ length: count }, (_, n) => line(n));

  it("keeps a short call whole", () => {
    assert.equal(windowOf(call(20)), call(20).join("\n"));
  });

  it("keeps the opening and the latest stretch of a long call, cut on whole lines", () => {
    const lines = call(400);
    const out = windowOf(lines).split("\n");
    assert.equal(out[0], lines[0]);
    assert.equal(out.at(-1), lines[399]);
    assert.ok(out.includes("[…]"));
    assert.ok(out.every((entry) => entry === "[…]" || lines.includes(entry)));
    assert.ok(out.join("\n").length <= 15100);
  });

  it("never comes back empty when one line is enormous", () => {
    const out = windowOf(["Them: hola", `Them: ${"y".repeat(30000)}`]);
    assert.ok(out.length > 0 && out.length <= 15100);
    assert.ok(out.endsWith("y"));
  });
});

describe("previousAnswers", () => {
  const card = (at: number, sayThis: string) => ({ ...draftCard("price", "es caro", at), sayThis });

  it("lists the lines already shown, oldest first, each once, without empty fillers", () => {
    assert.deepEqual(previousAnswers([card(1, "¿Caro comparado con qué?"), card(2, ""), card(3, "¿Caro comparado con qué?"), card(4, "¿Qué os cuesta hoy?")]), [
      "¿Caro comparado con qué?",
      "¿Qué os cuesta hoy?",
    ]);
  });

  it("keeps only the latest few", () => {
    const lines = Array.from({ length: 9 }, (_, i) => card(i, `línea ${i}`));
    assert.deepEqual(previousAnswers(lines), ["línea 3", "línea 4", "línea 5", "línea 6", "línea 7", "línea 8"]);
  });
});


describe("the cooldown after a card", () => {
  it("waits out the card being read, and not at all when none is up or it is over", () => {
    assert.equal(cooldownLeft(null, 5_000), 0);
    assert.equal(cooldownLeft(1_000, 1_000), CARD_COOLDOWN_MS);
    assert.equal(cooldownLeft(1_000, 5_000), CARD_COOLDOWN_MS - 4_000);
    assert.equal(cooldownLeft(1_000, 1_000 + CARD_COOLDOWN_MS + 1), 0);
  });

  it("defers the next check, never drops it: a new objection inside the cooldown is still checked after it", () => {
    // The first cooldown (a97cac99) marked their words as handled and dropped the turn, so this was never answered.
    const timing = checkTiming({ afterMs: 0, shownAt: 10_000, now: 13_000 });
    assert.deepEqual(timing, { waitMs: CARD_COOLDOWN_MS - 3_000, deferred: true });
    const turns = [turn("1", "prospect", "Es caro para nosotros."), turn("2", "rep", "Antes de números."), turn("3", "prospect", "Y además no lo decido yo.")];
    assert.equal(skipAnswered(timing.deferred, turns, "3"), false);
  });

  it("a check that did not have to wait runs as it always did", () => {
    const timing = checkTiming({ afterMs: 2_500, shownAt: null, now: 20_000 });
    assert.deepEqual(timing, { waitMs: 2_500, deferred: false });
    const answered = [turn("1", "prospect", "Es caro."), turn("2", "rep", "uno dos tres cuatro cinco seis siete ocho nueve diez")];
    assert.equal(skipAnswered(timing.deferred, answered, "1"), false);
  });

  it("a check that waited is skipped once the rep has answered them", () => {
    const answered = [
      turn("1", "prospect", "Me parece caro."),
      turn("2", "rep", "Claro, antes de hablar de números", "quiero ver cuánto tiempo os cuesta hoy"),
    ];
    assert.equal(repReplied(answered, "1"), true);
    assert.equal(skipAnswered(true, answered, "1"), true);
  });

  it("counts only the rep's words after their turn", () => {
    const words = "uno dos tres cuatro cinco seis siete ocho nueve";
    assert.equal(repReplied([turn("0", "rep", words), turn("1", "prospect", "Me parece caro.")], "1"), false);
    assert.equal(repReplied([turn("1", "prospect", "Me parece caro."), turn("2", "rep", "Vale, claro.")], "1"), false);
    assert.equal(repReplied([turn("1", "prospect", `${words} ${words}`), turn("2", "prospect", "y más")], "1"), false);
    assert.equal(repReplied([turn("1", "prospect", "Caro.")], "missing"), false);
  });
});
