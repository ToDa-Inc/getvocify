import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, meetingDisplayTurns, meetingRows, type MeetingTranscript } from "./meeting-transcript.ts";
import { NO_TEAM, teamSide } from "./meeting-team.ts";
import { SteadyTails } from "./steady-tail.ts";
import { OverlayFeed, withTeam } from "./overlay-turns.ts";

/**
 * A 60-minute call through the path the dashboard runs for each transcript update (see DesktopMeetingProvider's
 * sendOverlay): one Results message every 250 ms, a final every 4 s, speakers changing every 8-25 s, and the rep
 * talking over the other side for 6 s each minute. What goes to the desktop app is counted per update; it must not
 * grow with the length of the call.
 */
function simulate(minutes: number): { sends: { minute: number; bytes: number; turns: number }[]; builds: { minute: number; ms: number }[] } {
  const WORDS = "the price we can do that next week sure thanks budget timeline send over the proposal and check with legal".split(" ");
  let seed = 7;
  const random = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  const phrase = (count: number) => Array.from({ length: count }, () => WORDS[(random() * WORDS.length) | 0]).join(" ");

  const steady = new SteadyTails();
  const feed = new OverlayFeed();
  let transcript: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
  const sends: { minute: number; bytes: number; turns: number }[] = [];
  const builds: { minute: number; ms: number }[] = [];
  const TICK = 0.25;
  const PER_FINAL = 16;
  let prospectTalks = true;
  let turnEnd = 20;
  let utter: { words: string; step: number; start: number } | null = null;
  let clock = 0;

  const settle = (side: "rep" | "prospect", at: number, text: string) => {
    transcript = applyChannelResult(transcript, { text, isFinal: true, audioChannel: side, start: at, end: at + 3, name: side === "prospect" ? "Juan" : null });
  };

  for (let step = 0; step < minutes * 60 / TICK; step++) {
    clock += TICK;
    if (clock >= turnEnd) {
      if (utter) settle(prospectTalks ? "prospect" : "rep", utter.start, utter.words);
      prospectTalks = !prospectTalks;
      turnEnd = clock + 8 + random() * 17;
      utter = null;
    }
    const side = prospectTalks ? "prospect" : "rep";
    if (!utter) utter = { words: phrase(10), step: 0, start: clock };
    utter.step += 1;
    const isFinal = utter.step === PER_FINAL;
    const shown = utter.words.split(" ").slice(0, Math.max(1, Math.round((utter.step / PER_FINAL) * 10))).join(" ");
    transcript = applyChannelResult(transcript, {
      text: isFinal ? utter.words : shown,
      isFinal,
      audioChannel: side,
      start: utter.start,
      end: clock,
      name: side === "prospect" ? "Juan" : null,
    });
    if (isFinal) utter = null;
    const overlapping = clock % 60 > 30 && clock % 60 < 36;
    if (overlapping && !isFinal) transcript = applyChannelResult(transcript, { text: "yes sure", isFinal: false, audioChannel: "rep", start: clock, end: clock + 0.5 });
    if (clock % 60 >= 36 && clock % 60 < 36.25) transcript = applyChannelResult(transcript, { text: "yes sure", isFinal: true, audioChannel: "rep", start: clock - 6, end: clock });

    const speaking = { rep: side === "rep", prospect: side === "prospect" };
    const started = performance.now();
    const view = steady.view(transcript, clock * 1000);
    const change = feed.next(meetingDisplayTurns(view), { prospect: "Juan", language: "EN" }, false, speaking, "");
    builds.push({ minute: Math.floor(clock / 60) + 1, ms: performance.now() - started });
    if (change) {
      const payload = { from: change.from, turns: change.turns.slice(change.from) };
      sends.push({ minute: Math.floor(clock / 60) + 1, bytes: JSON.stringify(payload).length, turns: payload.turns.length });
    }
  }
  return { sends, builds };
}

describe("the overlay sent to the desktop app over a call", () => {
  it("costs the same per update at minute 60 as at minute 1", () => {
    const { sends, builds } = simulate(60);
    const average = (from: number, to: number, pick: (send: { bytes: number; turns: number }) => number) => {
      const inRange = sends.filter((send) => send.minute >= from && send.minute <= to);
      return inRange.reduce((sum, send) => sum + pick(send), 0) / inRange.length;
    };
    const bytesStart = average(1, 3, (send) => send.bytes);
    const bytesEnd = average(58, 60, (send) => send.bytes);
    const turnsStart = average(1, 3, (send) => send.turns);
    const turnsEnd = average(58, 60, (send) => send.turns);
    assert.ok(bytesEnd <= bytesStart * 2 + 100, `bytes per update grew from ${bytesStart.toFixed(0)} to ${bytesEnd.toFixed(0)}`);
    assert.ok(turnsEnd <= turnsStart * 2 + 2, `turns per update grew from ${turnsStart.toFixed(1)} to ${turnsEnd.toFixed(1)}`);
    // Building an update costs the same late in the call as early: medians of each window, with room for timing noise.
    const median = (values: number[]) => [...values].sort((a, b) => a - b)[values.length >> 1];
    const buildStart = median(builds.filter((b) => b.minute <= 3).map((b) => b.ms));
    const buildEnd = median(builds.filter((b) => b.minute >= 58).map((b) => b.ms));
    assert.ok(buildEnd <= buildStart * 3 + 0.05, `median build time grew from ${buildStart.toFixed(3)} ms to ${buildEnd.toFixed(3)} ms`);
    // No update sends the whole call again: the most turns any update resends stays small at the end of the call.
    const lateMost = Math.max(...sends.filter((send) => send.minute >= 30).map((send) => send.turns));
    assert.ok(lateMost < 12, `an update at minute 30 or later resent ${lateMost} turns`);
  });
});

describe("RowMemo and firstChanged with the same rows again", () => {
  it("return what they gave before without walking the rows", async () => {
    const { RowMemo, firstChanged } = await import("./overlay-turns.ts");
    const state = applyChannelResult(EMPTY_MEETING_TRANSCRIPT, { text: "Hola, qué tal", isFinal: true, audioChannel: "rep", start: 0, end: 1 });
    const rows = meetingDisplayTurns(state);
    assert.equal(meetingDisplayTurns(state), rows, "a transcript state has its rows once");
    const memo = new RowMemo<(typeof rows)[number], { key: string }>();
    const out = memo.update(rows, "EN", (row) => ({ key: row.key }));
    assert.equal(memo.update(rows, "EN", (row) => ({ key: row.key })), out);
    assert.equal(firstChanged(out, out), out.length);
  });
});

describe("a colleague in the meeting", () => {
  // Alexander is the guest; Toni (named by the meeting app) is the rep's colleague, heard on the same audio.
  let state: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
  state = applyChannelResult(state, { text: "Normalmente el outreach lo hacemos por LinkedIn.", isFinal: true, audioChannel: "prospect", start: 0, end: 3, name: "Alexander Schlacher" });
  state = applyChannelResult(state, { text: "¿Crees que esta es la llamada con más peso?", isFinal: true, audioChannel: "prospect", start: 4, end: 7, name: "TONI" });
  const team = teamSide(["Toni Mora"], ["Alexander Schlacher"]);

  it("is the rep's side for the live help, keeping their name", () => {
    const rows = meetingRows(state).slice().map((row) => withTeam(row, team));
    assert.deepEqual(rows.map((r) => [r.speaker, r.name, r.team ?? false]), [["prospect", "Alexander Schlacher", false], ["rep", "TONI", true]]);
    assert.equal(withTeam(rows[0], NO_TEAM), rows[0]);
  });

  it("reaches the island marked, still as a line of the other side's audio for an island that does not know the mark", () => {
    const sent = new OverlayFeed().next(meetingRows(state), { prospect: null, language: "ES", team }, true, {}, "")!;
    const turns = sent.turns.slice();
    assert.deepEqual(turns.map((t) => [t.you, t.label, t.team ?? false]), [[false, "Alexander Schlacher", false], [false, "TONI", true]]);
    // Without a team nothing is marked.
    const plain = new OverlayFeed().next(meetingRows(state), { prospect: null, language: "ES" }, true, {}, "")!;
    assert.equal(plain.turns.slice().some((t) => t.team), false);
  });
});
