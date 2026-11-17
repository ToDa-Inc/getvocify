import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, meetingDisplayTurns, type MeetingDisplayTurn, type MeetingTranscript } from "./meeting-transcript.ts";
import { draftSaveFor, type MeetingDraft, type SavedSegments } from "./meeting-draft.ts";
import { assistContext } from "./live-assist.ts";
import { MAX_TURNS, buildReading, repWords, toWireTurns } from "./live-brain.ts";
import { RowMemo } from "./overlay-turns.ts";
// @ts-expect-error the state module is plain JavaScript shared with the backend contract
import { emptyLiveState } from "../../shared/live-call/state.js";

/**
 * A 60-minute call through the work the dashboard does for each transcript update, and what it sends: the draft saved to
 * the desktop app every two seconds, the live help's checks on every render, and a live reading at each turn end. The
 * numbers at minute 60 must stay close to minute 1: what is new costs the same, whatever came before.
 */
type Sample = { minute: number; ms: number; bytes?: number };

function simulate(minutes: number): { updates: Sample[]; saves: Sample[]; readings: Sample[] } {
  const WORDS = "the price we can do that next week sure thanks budget timeline send over the proposal and check with legal".split(" ");
  let seed = 11;
  const random = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  const phrase = (count: number) => Array.from({ length: count }, () => WORDS[(random() * WORDS.length) | 0]).join(" ");

  const rows = new RowMemo<MeetingDisplayTurn, MeetingDisplayTurn>();
  let transcript: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
  let turns: MeetingDisplayTurn[] = [];
  let saved: SavedSegments = null;
  const draft = (state: MeetingTranscript): MeetingDraft => ({ id: "call-1", userId: "u", startedAt: 0, updatedAt: 0, transcript: state, notes: "" });
  const updates: Sample[] = [];
  const saves: Sample[] = [];
  const readings: Sample[] = [];
  const TICK = 0.25;
  const PER_FINAL = 16;
  let prospectTalks = true;
  let turnEnd = 20;
  let utter: { words: string; step: number; start: number } | null = null;
  let clock = 0;
  let lastSave = 0;

  for (let step = 0; step < (minutes * 60) / TICK; step++) {
    clock += TICK;
    if (clock >= turnEnd) {
      if (utter) transcript = applyChannelResult(transcript, { text: utter.words, isFinal: true, audioChannel: prospectTalks ? "prospect" : "rep", start: utter.start, end: utter.start + 3, name: prospectTalks ? "Juan" : null });
      prospectTalks = !prospectTalks;
      turnEnd = clock + 8 + random() * 17;
      utter = null;
      // A live reading at each turn end: the call as the backend gets it.
      const started = performance.now();
      const wire = toWireTurns(turns);
      const body = buildReading({ call: { callId: "call-1", callMode: "meeting" }, turns: wire, state: emptyLiveState("call-1"), reason: "turn_end", producer: "progress" });
      const bytes = JSON.stringify(body).length;
      readings.push({ minute: Math.floor(clock / 60) + 1, ms: performance.now() - started, bytes });
      assert.ok(wire.length <= MAX_TURNS, "a reading sends at most the backend's turns");
    }
    if (!utter) utter = { words: phrase(10), step: 0, start: clock };
    utter.step += 1;
    const isFinal = utter.step === PER_FINAL;
    const shown = utter.words.split(" ").slice(0, Math.max(1, Math.round((utter.step / PER_FINAL) * 10))).join(" ");
    const next = applyChannelResult(transcript, {
      text: isFinal ? utter.words : shown,
      isFinal,
      audioChannel: prospectTalks ? "prospect" : "rep",
      start: utter.start,
      end: clock,
      name: prospectTalks ? "Juan" : null,
    });
    if (isFinal) utter = null;
    if (next === transcript) continue;
    transcript = next;

    // What the dashboard does for an update: its turns, and the live help's checks that run on the render.
    const started = performance.now();
    turns = rows.update(meetingDisplayTurns(transcript), "EN", (turn) => ({ ...turn }));
    assistContext(turns, null);
    repWords(turns);
    updates.push({ minute: Math.floor(clock / 60) + 1, ms: performance.now() - started });

    // The draft, every two seconds, as the desktop app receives it.
    if (clock - lastSave >= 2) {
      lastSave = clock;
      const save = draftSaveFor(draft(transcript), saved, true);
      const startedSave = performance.now();
      const bytes = JSON.stringify(save).length;
      saves.push({ minute: Math.floor(clock / 60) + 1, ms: performance.now() - startedSave, bytes });
      if (saves.length > 1) assert.equal(save.kind, "append", "only the first save is the whole draft");
      saved = { id: "call-1", segments: transcript.segments };
    }
  }
  return { updates, saves, readings };
}

const median = (values: number[]) => [...values].sort((a, b) => a - b)[values.length >> 1];
const inMinutes = (samples: Sample[], from: number, to: number) => samples.filter((sample) => sample.minute >= from && sample.minute <= to);

describe("a 60-minute call costs the same per update at minute 60 as at minute 1", () => {
  const { updates, saves, readings } = simulate(60);

  it("the live help's work per update", () => {
    const start = median(inMinutes(updates, 1, 3).map((sample) => sample.ms));
    const end = median(inMinutes(updates, 58, 60).map((sample) => sample.ms));
    assert.ok(end <= start * 3 + 0.05, `median work per update grew from ${start.toFixed(3)} ms to ${end.toFixed(3)} ms`);
  });

  it("the draft posted to the desktop app per save", () => {
    const start = median(inMinutes(saves, 1, 3).map((sample) => sample.bytes ?? 0));
    const end = median(inMinutes(saves, 58, 60).map((sample) => sample.bytes ?? 0));
    assert.ok(end <= start * 2 + 200, `bytes per draft save grew from ${start} to ${end}`);
  });

  it("a live reading is bounded by the backend's turn limit (it grows with the call until then)", () => {
    const bytes = readings.map((sample) => sample.bytes ?? 0);
    const cap = Math.max(...bytes);
    assert.ok(cap > 0 && cap < MAX_TURNS * 4500, `a reading was ${cap} bytes`);
  });
});
