import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyChannelResult,
  meetingTurns,
  EMPTY_MEETING_TRANSCRIPT,
  meetingDisplayTurns,
  meetingLastLine,
  meetingUploadText,
  resetChannel,
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
  it("keeps a bubble's key from its first word to its final", () => {
    const live = feed([["hola", true, "rep"], ["buenas", false, "prospect"]]);
    const rows = meetingDisplayTurns(live);
    assert.deepEqual(rows.map((r) => [r.key, r.label, r.text, r.pending]), [
      ["u0", "You", "hola", ""],
      ["u1", "Them", "", "buenas"],
    ]);
    const settled = meetingDisplayTurns(applyChannelResult(live, { text: "buenas tardes", isFinal: true, audioChannel: "prospect" }));
    assert.deepEqual(settled.map((r) => [r.key, r.text, r.pending]), [["u0", "hola", ""], ["u1", "buenas tardes", ""]]);
  });

  it("never moves or splits a bubble on screen when a late final was spoken earlier", () => {
    const events: Array<[string, boolean, string, number]> = [
      ["Which", true, "prospect", 10],
      ["is it", false, "prospect", 12],
      ["is it?", true, "prospect", 12],
      ["Yes.", true, "rep", 11],
    ];
    const state = events.reduce(
      (acc, [text, isFinal, audioChannel, start]) => applyChannelResult(acc, { text, isFinal, audioChannel, start, end: start + 1 }),
      EMPTY_MEETING_TRANSCRIPT,
    );
    assert.deepEqual(meetingDisplayTurns(state).map((r) => [r.key, r.text]), [["u0", "Which is it?"], ["u2", "Yes."]]);
    // The saved transcript still reads in the order things were said.
    assert.deepEqual(meetingTurns(state).map((t) => t.text), ["Which", "Yes.", "is it?"]);
  });

  it("puts both live tails in the order they started and keeps them there", () => {
    const state = feed([["te cuento", false, "rep"], ["perfecto", false, "prospect"], ["te cuento el precio", false, "rep"]]);
    assert.deepEqual(meetingDisplayTurns(state).map((r) => [r.key, r.pending]), [["u0", "te cuento el precio"], ["u1", "perfecto"]]);
    const repDone = applyChannelResult(state, { text: "Te cuento el precio.", isFinal: true, audioChannel: "rep" });
    assert.deepEqual(meetingDisplayTurns(repDone).map((r) => [r.key, r.text, r.pending]), [
      ["u0", "Te cuento el precio.", ""],
      ["u1", "", "perfecto"],
    ]);
  });

  it("continues the same speaker's paragraph instead of opening a new one", () => {
    const rows = meetingDisplayTurns(feed([["hola", true, "rep"], ["qué tal", false, "rep"]]));
    assert.equal(rows.length, 1);
    assert.equal(rows[0].pending, "qué tal");
  });

  it("shows drafts saved before bubbles had a place in arrival order", async () => {
    const { normalizeMeetingTranscript } = await import("./meeting-transcript.ts");
    const old = normalizeMeetingTranscript({
      segments: [
        { speaker: "prospect", text: "Hola", start: 5, end: 6 },
        { speaker: "rep", text: "Buenas", start: 2, end: 3 },
      ],
      interims: {},
    });
    assert.deepEqual(meetingDisplayTurns(old).map((r) => [r.key, r.text]), [["u0", "Hola"], ["u1", "Buenas"]]);
    const next = applyChannelResult(old, { text: "Qué tal", isFinal: true, audioChannel: "prospect" });
    assert.deepEqual(meetingDisplayTurns(next).map((r) => r.key), ["u0", "u1", "u2"]);
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
  it("sends the whole conversation, untrimmed, with each pending tail", async () => {
    const { meetingOverlay } = await import("./meeting-transcript.ts");
    const long = "Uno dos tres cuatro cinco seis siete ocho nueve diez. ".repeat(6).trim();
    const state = feed([
      ["Buenas.", true, "rep"],
      [long, true, "prospect"],
      ["Vale.", true, "rep"],
      ["Sí.", true, "prospect"],
      ["Te cuento", false, "rep"],
    ]);
    const { turns } = meetingOverlay(state);
    assert.deepEqual(turns.map((t) => [t.you, t.text, t.pending]), [
      [true, "Buenas.", ""],
      [false, long, ""],
      [true, "Vale.", ""],
      [false, "Sí.", ""],
      [true, "", "Te cuento"],
    ]);
  });

  it("is empty before anyone speaks", async () => {
    const { meetingOverlay } = await import("./meeting-transcript.ts");
    assert.deepEqual(meetingOverlay(EMPTY_MEETING_TRANSCRIPT), { turns: [] });
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

  it("settles a tail cut off at stop where it was said, not at the end", () => {
    const live = [
      { text: "Hola, te cuento", isFinal: false, audioChannel: "rep", start: 3, end: 4 },
      { text: "Vale, perfecto.", isFinal: true, audioChannel: "prospect", start: 6, end: 7 },
    ].reduce(applyChannelResult, EMPTY_MEETING_TRANSCRIPT);
    assert.equal(meetingUploadText(live), "SPEAKER: S1\nHola, te cuento\n\nSPEAKER: S2\nVale, perfecto.");
  });

  it("removes echo from the uploaded transcript too", () => {
    const state = timed([
      ["Pick the screen, select the screen.", "prospect", 5, 7],
      ["select the screen", "rep", 6, 7],
    ]);
    assert.equal(meetingUploadText(state), "SPEAKER: S2\nPick the screen, select the screen.");
  });
});

describe("resetChannel", () => {
  it("drops one side's words from the restart on and keeps everything else", () => {
    const state = [
      { text: "Hola", isFinal: true, audioChannel: "rep", start: 1, end: 2 },
      { text: "Bon dia Jordi", isFinal: true, audioChannel: "prospect", start: 2, end: 3 },
      { text: "Gracias per", isFinal: false, audioChannel: "prospect", start: 4, end: 5 },
    ].reduce(applyChannelResult, EMPTY_MEETING_TRANSCRIPT);
    const reset = resetChannel(state, "prospect", 0);
    assert.deepEqual(meetingTurns(reset), [{ speaker: "rep", text: "Hola" }]);
    assert.deepEqual(reset.interims, {});
    const again = applyChannelResult(reset, { text: "Bon dia, Jordi.", isFinal: true, audioChannel: "prospect", start: 2, end: 3 });
    assert.deepEqual(meetingTurns(again).map((t) => t.text), ["Hola", "Bon dia, Jordi."]);
  });

  it("keeps what was said before a mid-call restart", () => {
    const state = [
      { text: "Primero", isFinal: true, audioChannel: "prospect", start: 1, end: 2 },
      { text: "després", isFinal: true, audioChannel: "prospect", start: 50, end: 51 },
    ].reduce(applyChannelResult, EMPTY_MEETING_TRANSCRIPT);
    assert.deepEqual(meetingTurns(resetChannel(state, "prospect", 48)).map((t) => t.text), ["Primero"]);
    assert.equal(resetChannel(state, "nobody", 0), state);
  });
});

describe("echo while still being written", () => {
  it("hides the mic's tail when it repeats the call, and keeps the rep's own words", () => {
    const state = [
      { text: "departamentos de captación", isFinal: false, audioChannel: "prospect", start: 40, end: 41 },
      { text: "departamentos de", isFinal: false, audioChannel: "rep", start: 40.2, end: 41 },
    ].reduce(applyChannelResult, EMPTY_MEETING_TRANSCRIPT);
    assert.deepEqual(meetingDisplayTurns(state).map((row) => row.speaker), ["prospect"]);
    const own = applyChannelResult(state, { text: "te paso la propuesta", isFinal: false, audioChannel: "rep", start: 41 });
    assert.deepEqual(meetingDisplayTurns(own).map((row) => row.speaker), ["prospect", "rep"]);
  });
});

describe("paragraphs", () => {
  const timed = (events: Array<[string, string, number, number]>) =>
    events.reduce(
      (state, [text, audioChannel, start, end]) => applyChannelResult(state, { text, isFinal: true, audioChannel, start, end }),
      EMPTY_MEETING_TRANSCRIPT,
    );

  it("a short reaction said over someone keeps its bubble but doesn't cut their paragraph", () => {
    const state = timed([
      ["Lo que hacemos es escuchar la llamada", "rep", 10, 12],
      ["Vale.", "prospect", 11.5, 11.8],
      ["y proponer los cambios en el CRM.", "rep", 12.2, 14],
    ]);
    assert.deepEqual(meetingDisplayTurns(state).map((row) => row.text), [
      "Lo que hacemos es escuchar la llamada y proponer los cambios en el CRM.",
      "Vale.",
    ]);
    // The saved transcript keeps the exact order.
    assert.equal(meetingTurns(state).length, 3);
  });

  it("an answer after the speaker stopped is a turn of its own", () => {
    const state = timed([
      ["¿Quedamos el martes?", "rep", 10, 11],
      ["Sí.", "prospect", 12.5, 12.8],
      ["Perfecto, te mando la invitación.", "rep", 13.5, 15],
    ]);
    assert.equal(meetingDisplayTurns(state).length, 3);
  });
});

describe("names on the other side", () => {
  it("labels each person the Mac app saw speaking and starts a paragraph when it changes", async () => {
    const { normalizeMeetingTranscript } = await import("./meeting-transcript.ts");
    const state = normalizeMeetingTranscript({
      segments: [
        { speaker: "prospect", text: "Hola, soy Marta.", start: 1, end: 2, seen: 0, name: "Marta" },
        { speaker: "prospect", text: "Y yo Juan.", start: 3, end: 4, seen: 1, name: "Juan" },
        { speaker: "rep", text: "Encantado.", start: 5, end: 6, seen: 2, name: null },
      ],
      interims: {},
      nextSeen: 3,
    });
    assert.deepEqual(meetingDisplayTurns(state).map((row) => row.label), ["Marta", "Juan", "You"]);
  });
});

describe("bubbles never jump", () => {
  it("a tail settling after the other side's final keeps its place", () => {
    let state = feed([["lo que te decía es que", false, "prospect"], ["Ajá, vale", false, "rep"], ["Ajá, vale.", true, "rep"]]);
    const before = meetingDisplayTurns(state).map((row) => row.key);
    state = applyChannelResult(state, { text: "lo que te decía es que funciona.", isFinal: true, audioChannel: "prospect" });
    assert.deepEqual(meetingDisplayTurns(state).map((row) => row.key), before);
    assert.deepEqual(meetingDisplayTurns(state).map((row) => row.speaker), ["prospect", "rep"]);
  });

  it("the words a final doesn't cover stay in the same bubble", () => {
    let state = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "hola qué tal estás", isFinal: false, audioChannel: "rep", start: 1, end: 2.4 });
    state = applyChannelResult(state, { text: "Hola, qué tal", isFinal: true, audioChannel: "rep", start: 1, end: 2 });
    assert.deepEqual(meetingDisplayTurns(state).map((row) => [row.key, row.text, row.pending]), [["u0", "Hola, qué tal", "estás"]]);
    state = applyChannelResult(state, { text: "estás?", isFinal: true, audioChannel: "rep", start: 2, end: 2.5 });
    assert.deepEqual(meetingDisplayTurns(state).map((row) => [row.key, row.text, row.pending]), [["u0", "Hola, qué tal estás?", ""]]);
  });

  it("a final for the whole tail that drops a word leaves nothing behind", () => {
    let state = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "vale vale perfecto", isFinal: false, audioChannel: "rep", start: 1, end: 2 });
    state = applyChannelResult(state, { text: "Vale, perfecto.", isFinal: true, audioChannel: "rep", start: 1, end: 2 });
    assert.deepEqual(meetingDisplayTurns(state).map((row) => [row.text, row.pending]), [["Vale, perfecto.", ""]]);
  });
});
