import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyChannelResult,
  meetingTurns,
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
    assert.deepEqual(meetingTurns(state), [{ speaker: "prospect", text: "Quedamos el martes" }]);
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
    assert.deepEqual(meetingTurns(state), [{ speaker: "rep", text: "hola, qué tal bien" }]);
  });

  it("ignores empty and repeated events without touching settled text", () => {
    const base = feed([["hola", true, "rep"], ["qué", false, "prospect"]]);
    assert.equal(applyChannelResult(base, { text: "  ", isFinal: false, audioChannel: "rep" }), base);
    assert.equal(applyChannelResult(base, { text: "qué", isFinal: false, audioChannel: "prospect" }), base);
    const closed = applyChannelResult(base, { text: "", isFinal: true, audioChannel: "prospect" });
    assert.deepEqual(meetingTurns(closed), meetingTurns(base));
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
    assert.equal(meetingUploadText(state), "SPEAKER: S1\nhola qué\n\nSPEAKER: S2\nbuenas");
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

describe("desktop upload format", () => {
  it("parses into You/Them bubbles on the memo page", async () => {
    const { parseTranscriptTurns, normalizeDiarizedTranscript, speakerSide } = await import("./transcript-turns.ts");
    const text = meetingUploadText(feed([["hola", true, "rep"], ["buenas", true, "prospect"], ["te cuento", true, "rep"]]));
    const turns = parseTranscriptTurns(normalizeDiarizedTranscript(text));
    assert.deepEqual(turns.map((t) => [speakerSide(t.speaker), t.text]), [["s1", "hola"], ["s2", "buenas"], ["s1", "te cuento"]]);
  });
});

describe("phraseTail", () => {
  it("returns short text untouched", async () => {
    const { phraseTail } = await import("./meeting-transcript.ts");
    assert.equal(phraseTail("Abrazo, chicos.", 40), "Abrazo, chicos.");
  });

  it("starts at the latest sentence that fits instead of mid-word", async () => {
    const { phraseTail } = await import("./meeting-transcript.ts");
    const text = "Perfecto, tío. Cuando lo vayamos probando os decimos, vale. Pues os paso esto.";
    assert.equal(phraseTail(text, 50), "…Pues os paso esto.");
  });

  it("falls back to a word boundary inside one long sentence", async () => {
    const { phraseTail } = await import("./meeting-transcript.ts");
    const tail = phraseTail("uno dos tres cuatro cinco seis siete ocho nueve diez", 20);
    assert.equal(tail, "…ocho nueve diez");
  });
});

describe("meetingOverlay", () => {
  it("keeps the last turns with their speaker and styled pending tail", async () => {
    const { meetingOverlay } = await import("./meeting-transcript.ts");
    const state = feed([
      ["Buenas.", true, "rep"],
      ["Hola, qué tal.", true, "prospect"],
      ["Te cuento", false, "rep"],
    ]);
    const { line, lineLabel, recent } = meetingOverlay(state, { turns: 2 });
    assert.equal(line, "Te cuento");
    assert.equal(lineLabel, "You");
    assert.deepEqual(recent.map((t) => [t.you, t.text, t.pending]), [
      [false, "Hola, qué tal.", ""],
      [true, "", "Te cuento"],
    ]);
  });

  it("is empty before anyone speaks", async () => {
    const { meetingOverlay } = await import("./meeting-transcript.ts");
    assert.deepEqual(meetingOverlay(EMPTY_MEETING_TRANSCRIPT), { line: "", lineLabel: null, recent: [] });
  });
});

describe("fragments without a channel", () => {
  it("never become their own unlabeled turn", () => {
    const state = feed([
      ["This", true, ""],
      ["was much better.", true, "prospect"],
      ["Yeah", true, "rep"],
      ["right.", true, ""],
    ]);
    assert.deepEqual(meetingTurns(state), [
      { speaker: "prospect", text: "This was much better." },
      { speaker: "rep", text: "Yeah right." },
    ]);
  });
});

describe("speech-time order and echo", () => {
  const timed = (events: Array<[string, string, number, number]>) =>
    events.reduce(
      (state, [text, audioChannel, start, end]) => applyChannelResult(state, { text, isFinal: true, audioChannel, start, end }),
      EMPTY_MEETING_TRANSCRIPT,
    );

  it("places a late-arriving final where it was spoken", () => {
    // Their "is Oh, I know where to start" arrives before our earlier "Yes. That's right."
    const state = timed([
      ["Which", "prospect", 10, 10.4],
      ["is. Oh, I know where to start.", "prospect", 12, 13.5],
      ["Yes. That's right.", "rep", 10.6, 11.4],
    ]);
    assert.deepEqual(meetingTurns(state), [
      { speaker: "prospect", text: "Which" },
      { speaker: "rep", text: "Yes. That's right." },
      { speaker: "prospect", text: "is. Oh, I know where to start." },
    ]);
  });

  it("drops the mic hearing the meeting through the speakers", () => {
    const state = timed([
      ["This was much better than the last one.", "prospect", 20, 22],
      ["than", "rep", 21.2, 21.4],
      ["much better than", "rep", 21, 21.6],
    ]);
    assert.deepEqual(meetingTurns(state), [{ speaker: "prospect", text: "This was much better than the last one." }]);
  });

  it("keeps the rep's own words even while the other side talks", () => {
    const state = timed([
      ["We need a system to help them start.", "prospect", 30, 33],
      ["Sure, I will send the course today.", "rep", 31, 33],
    ]);
    assert.equal(meetingTurns(state).length, 2);
  });

  it("removes echo from the uploaded transcript too", () => {
    const state = timed([
      ["Pick the screen, select the screen.", "prospect", 5, 7],
      ["select the screen", "rep", 6, 7],
    ]);
    assert.equal(meetingUploadText(state), "SPEAKER: S2\nPick the screen, select the screen.");
  });
});
