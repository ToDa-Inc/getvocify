import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, meetingDisplayTurns, type MeetingTranscript } from "./meeting-transcript.ts";
import { proposalLines, proposalWords } from "./proposal-lines.ts";

const settled = (state: MeetingTranscript) => meetingDisplayTurns({ segments: state.segments, voiceNames: state.voiceNames, interims: {} });
const wordsOfLines = (state: MeetingTranscript, language: "EN" | "ES") =>
  proposalLines(settled(state), language).reduce((sum, line) => sum + line.split(/\s+/).length, 0);

describe("proposalWords", () => {
  it("counts the words of the proposal's lines as the call goes on, in either language", () => {
    let state = EMPTY_MEETING_TRANSCRIPT;
    const lines = ["Hola, qué tal", "Bien, mirando precios", "y el equipo", "Vale.", "Os cuento la demo ahora mismo"];
    lines.forEach((text, index) => {
      // The same side twice in a row: the second final joins its paragraph (a row that changes).
      state = applyChannelResult(state, { text, isFinal: true, audioChannel: index === 2 || index % 2 === 0 ? "rep" : "prospect", start: index * 3, end: index * 3 + 2 });
      for (const language of ["EN", "ES"] as const) assert.equal(proposalWords(settled(state), language), wordsOfLines(state, language), `after line ${index}, ${language}`);
    });
  });

  it("counts nothing for an empty call", () => {
    assert.equal(proposalWords(settled(EMPTY_MEETING_TRANSCRIPT), "EN"), 0);
  });
});
