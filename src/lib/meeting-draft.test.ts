import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, type MeetingSegment, type MeetingTranscript } from "./meeting-transcript.ts";
import { draftSaveFor, type MeetingDraft, type SavedSegments } from "./meeting-draft.ts";

const draftWith = (transcript: MeetingTranscript, id = "m-1"): MeetingDraft => ({ id, userId: "u", startedAt: 1, updatedAt: 2, transcript, notes: "" });

/** Lines the desktop app keeps for a draft, as its append protocol rebuilds them: the saved segments, then each append. */
function replay(base: MeetingDraft, saves: ReturnType<typeof draftSaveFor>[]): MeetingSegment[] {
  let segments = base.transcript.segments;
  for (const save of saves) {
    if (save.kind === "full") segments = save.draft.transcript.segments;
    else segments = [...segments, ...save.segments];
  }
  return segments;
}

describe("a draft save sends what is new", () => {
  it("sends the whole draft first, then only the segments after the ones saved", () => {
    let transcript: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
    let saved: SavedSegments = null;
    const saves: ReturnType<typeof draftSaveFor>[] = [];
    for (let step = 0; step < 40; step++) {
      transcript = applyChannelResult(transcript, { text: `line ${step} here`, isFinal: step % 3 === 2, audioChannel: step % 2 ? "rep" : "prospect", start: step, end: step + 1 });
      const save = draftSaveFor(draftWith(transcript), saved, true);
      saves.push(save);
      saved = { id: "m-1", segments: transcript.segments };
    }
    assert.equal(saves[0].kind, "full");
    for (const save of saves.slice(1)) {
      assert.equal(save.kind, "append");
      if (save.kind === "append") assert.ok(save.segments.length <= 1, "a save adds at most the finals since the last one");
    }
    assert.deepEqual(replay(draftWith(EMPTY_MEETING_TRANSCRIPT), saves), transcript.segments);
  });

  it("sends the whole draft when the desktop app does not keep appends, or the draft is another one", () => {
    const transcript = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "hola", isFinal: true, audioChannel: "rep", start: 0, end: 1 });
    const saved = { id: "m-1", segments: transcript.segments };
    assert.equal(draftSaveFor(draftWith(transcript), saved, false).kind, "full");
    assert.equal(draftSaveFor(draftWith(transcript, "m-2"), saved, true).kind, "full");
    assert.equal(draftSaveFor(draftWith(transcript), null, true).kind, "full");
  });

  it("sends the whole draft when a saved line was edited (a voice) or the segments were cut", () => {
    const first = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "uno", isFinal: true, audioChannel: "prospect", start: 0, end: 1 });
    const grown = applyChannelResult(first, { text: "dos", isFinal: true, audioChannel: "prospect", start: 2, end: 3 });
    const saved = { id: "m-1", segments: grown.segments };
    const edited: MeetingTranscript = { ...grown, segments: [{ ...grown.segments[0], voice: 2 }, grown.segments[1]] };
    assert.equal(draftSaveFor(draftWith(edited), saved, true).kind, "full");
    assert.equal(draftSaveFor(draftWith(first), saved, true).kind, "full");
  });

  it("an interim alone sends no segments, but the rest of the draft", () => {
    const transcript = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "hola", isFinal: true, audioChannel: "rep", start: 0, end: 1 });
    const typing = applyChannelResult(transcript, { text: "buenas", isFinal: false, audioChannel: "prospect", start: 2, end: 2.5 });
    const save = draftSaveFor(draftWith(typing), { id: "m-1", segments: transcript.segments }, true);
    assert.equal(save.kind, "append");
    if (save.kind === "append") {
      assert.deepEqual(save.segments, []);
      assert.equal(save.from, 1);
      assert.deepEqual(save.draft.transcript.interims, { prospect: "buenas" });
      assert.equal("segments" in save.draft.transcript, false);
    }
  });
});
