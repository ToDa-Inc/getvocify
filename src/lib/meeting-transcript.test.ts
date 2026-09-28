import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyChannelResult,
  EMPTY_MEETING_TRANSCRIPT,
  meetingDisplayTurns,
  meetingLastLine,
  meetingUploadText,
  type MeetingTranscript,
} from "./meeting-transcript.ts";
import { draftMinutes, sortDrafts, type MeetingDraft } from "./meeting-draft.ts";

const feed = (events: Array<[string, boolean, string]>): MeetingTranscript =>
  events.reduce(
    (state, [text, isFinal, audioChannel]) => applyChannelResult(state, { text, isFinal, audioChannel }),
    EMPTY_MEETING_TRANSCRIPT,
  );

describe("applyChannelResult", () => {
  it("replaces the interim with its final exactly once", () => {
    const state = feed([
      ["Quedamos el mar", false, "prospect"],
      ["Quedamos el martes", true, "prospect"],
    ]);
    assert.deepEqual(state.turns, [{ speaker: "prospect", text: "Quedamos el martes" }]);
    assert.deepEqual(state.interims, {});
  });

  it("keeps each channel's interim when both talk at once", () => {
    const state = feed([
      ["te cuento", false, "rep"],
      ["perfecto", false, "prospect"],
      ["te cuento el precio", false, "rep"],
    ]);
    assert.deepEqual(state.interims, { rep: "te cuento el precio", prospect: "perfecto" });
  });

  it("joins same-speaker finals into one readable paragraph", () => {
    const state = feed([
      ["hola", true, "rep"],
      [", qué tal", true, "rep"],
      ["bien", true, "rep"],
    ]);
    assert.deepEqual(state.turns, [{ speaker: "rep", text: "hola, qué tal bien" }]);
  });

  it("ignores empty and repeated events without touching settled text", () => {
    const base = feed([["hola", true, "rep"], ["qué", false, "prospect"]]);
    assert.equal(applyChannelResult(base, { text: "  ", isFinal: false, audioChannel: "rep" }), base);
    assert.equal(applyChannelResult(base, { text: "qué", isFinal: false, audioChannel: "prospect" }), base);
    const closed = applyChannelResult(base, { text: "", isFinal: true, audioChannel: "prospect" });
    assert.deepEqual(closed.turns, base.turns);
    assert.deepEqual(closed.interims, {});
  });
});

describe("meetingDisplayTurns", () => {
  it("keeps settled keys stable and gives a pending paragraph its future key", () => {
    const live = feed([["hola", true, "rep"], ["buenas", false, "prospect"]]);
    const rows = meetingDisplayTurns(live);
    assert.deepEqual(rows.map((r) => [r.key, r.label, r.text, r.pending]), [
      ["0", "You", "hola", ""],
      ["1", "Them", "", "buenas"],
    ]);
    const settled = meetingDisplayTurns(applyChannelResult(live, { text: "buenas tardes", isFinal: true, audioChannel: "prospect" }));
    assert.deepEqual(settled.map((r) => [r.key, r.text, r.pending]), [["0", "hola", ""], ["1", "buenas tardes", ""]]);
  });

  it("continues the same speaker's paragraph instead of opening a new one", () => {
    const rows = meetingDisplayTurns(feed([["hola", true, "rep"], ["qué tal", false, "rep"]]));
    assert.equal(rows.length, 1);
    assert.equal(rows[0].pending, "qué tal");
  });
});

describe("meetingUploadText", () => {
  it("settles unfinished tails so nothing said is dropped at stop", () => {
    const state = feed([["hola", true, "rep"], ["qué", false, "rep"], ["buenas", false, "prospect"]]);
    assert.equal(meetingUploadText(state), "You: hola qué\n\nThem: buenas");
    assert.equal(meetingLastLine(state), "buenas");
  });

  it("is empty when nothing was said", () => {
    assert.equal(meetingUploadText(EMPTY_MEETING_TRANSCRIPT), "");
  });
});

describe("sortDrafts", () => {
  const draft = (id: string, userId: string, startedAt: number, text: string): MeetingDraft => ({
    id,
    userId,
    startedAt,
    updatedAt: startedAt + 25 * 60000,
    transcript: text ? { turns: [{ speaker: "rep", text }], interims: {} } : { turns: [], interims: {} },
  });

  it("sends the user's meetings oldest first and discards empty ones", () => {
    const { send, discard } = sortDrafts(
      [draft("b", "u1", 2, "dos"), draft("a", "u1", 1, "uno"), draft("c", "u1", 3, ""), draft("d", "u2", 0, "otro"), { junk: true }],
      "u1",
    );
    assert.deepEqual(send.map((d) => d.id), ["a", "b"]);
    assert.deepEqual(discard.map((d) => d.id), ["c"]);
  });

  it("rounds meeting length to whole minutes, at least one", () => {
    assert.equal(draftMinutes(draft("a", "u1", 0, "x")), 25);
    assert.equal(draftMinutes({ ...draft("a", "u1", 0, "x"), updatedAt: 1000 }), 1);
  });
});
