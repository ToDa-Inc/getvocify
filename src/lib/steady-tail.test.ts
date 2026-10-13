import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { SteadyTails } from "./steady-tail.ts";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, type MeetingTranscript } from "./meeting-transcript.ts";

const guess = (state: MeetingTranscript, text: string) => applyChannelResult(state, { text, isFinal: false, audioChannel: "prospect" });
const final = (state: MeetingTranscript, text: string) => applyChannelResult(state, { text, isFinal: true, audioChannel: "prospect" });
const shown = (tails: SteadyTails, state: MeetingTranscript, now: number) => tails.view(state, now).interims.prospect ?? "";

describe("SteadyTails", () => {
  it("shows words once they stop changing, the first one too", () => {
    const tails = new SteadyTails(500);
    let s = guess(EMPTY_MEETING_TRANSCRIPT, "Oh.");
    assert.equal(shown(tails, s, 0), "");
    s = guess(s, "Hola");
    assert.equal(shown(tails, s, 100), "");
    assert.equal(shown(tails, s, 650), "Hola");
    s = guess(s, "Hola qué");
    assert.equal(shown(tails, s, 700), "Hola");
    s = guess(s, "Hola que tal");
    assert.equal(shown(tails, s, 900), "Hola");
    assert.equal(shown(tails, s, 1250), "Hola que");
    assert.equal(shown(tails, s, 1500), "Hola que tal");
  });

  it("never takes back a shown word while the guess changes its mind", () => {
    const tails = new SteadyTails(500);
    let s = guess(EMPTY_MEETING_TRANSCRIPT, "Què collons està passant");
    shown(tails, s, 0);
    assert.equal(shown(tails, s, 600), "Què collons està passant");
    s = guess(s, "Què està passant");
    assert.equal(shown(tails, s, 700), "Què collons està passant");
    s = guess(s, "Què hauria d'estar passant");
    assert.equal(shown(tails, s, 800), "Què collons està passant");
  });

  it("keeps the rest of the sentence on screen while a final settles its start", () => {
    const tails = new SteadyTails(500);
    let s = guess(EMPTY_MEETING_TRANSCRIPT, "No sé si te acuerdas");
    shown(tails, s, 0);
    assert.equal(shown(tails, s, 600), "No sé si te acuerdas");
    s = final(s, "No sé si te");
    assert.equal(shown(tails, s, 650), "acuerdas");
    s = guess(s, "acuerdas de mí");
    assert.equal(shown(tails, s, 700), "acuerdas");
    assert.equal(shown(tails, s, 1300), "acuerdas de mí");
    // Nothing continues it: it goes after a moment.
    s = final(s, "acuerdas de mí.");
    assert.equal(shown(tails, s, 5000), "");
  });

  it("never touches the transcript itself", () => {
    const tails = new SteadyTails(500);
    const s = guess(EMPTY_MEETING_TRANSCRIPT, "Hola que tal");
    tails.view(s, 0);
    assert.equal(s.interims.prospect, "Hola que tal");
  });
});
