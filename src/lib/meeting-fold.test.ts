import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, applyVoice, EMPTY_MEETING_TRANSCRIPT, forgetFolds, meetingDisplayTurns, renameVoice, type MeetingTranscript } from "./meeting-transcript.ts";

/**
 * The transcript on screen is built incrementally (a final extends what was built before). Over random calls it must show
 * exactly what a build from scratch shows, after every update.
 */
describe("the incremental transcript matches a build from scratch", () => {
  it("over random calls: finals, interims, echoes, voices and names", () => {
    const WORDS = "yes no maybe the price we can do that next week sure thanks budget timeline".split(" ");
    for (let run = 0; run < 25; run++) {
      let seed = run + 1;
      const random = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
      const pick = <T,>(items: T[]) => items[(random() * items.length) | 0];
      let state: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
      let clock = 0;
      for (let step = 0; step < 150; step++) {
        const roll = random();
        clock += random() * 2;
        if (roll < 0.55) {
          const text = Array.from({ length: 1 + ((random() * 8) | 0) }, () => pick(WORDS)).join(" ") + (random() < 0.3 ? "." : "");
          state = applyChannelResult(state, {
            text,
            isFinal: random() < 0.4,
            audioChannel: pick(["rep", "prospect"]),
            start: clock,
            end: clock + random() * 3,
            name: random() < 0.3 ? pick(["Marta", "Juan"]) : null,
          });
        } else if (roll < 0.7) {
          state = applyVoice(state, clock - random() * 2, 1 + ((random() * 3) | 0));
        } else if (roll < 0.8) {
          state = renameVoice(state, 1 + ((random() * 3) | 0), pick(["Laura", "Marta", ""]));
        }
        // What the rows show after this update, built incrementally and then from scratch.
        const incremental = JSON.stringify(meetingDisplayTurns(state));
        forgetFolds();
        const scratch = JSON.stringify(meetingDisplayTurns(state));
        assert.equal(incremental, scratch, `run ${run}, step ${step}`);
      }
    }
  });
});

describe("the rows of an earlier update never change under whoever holds them", () => {
  it("over long random calls, with lines settling into the shared rows and echoes reaching back", async () => {
    const { meetingRows } = await import("./meeting-transcript.ts");
    const WORDS = "yes no maybe the price we can do that next week sure thanks budget timeline".split(" ");
    for (let run = 0; run < 6; run++) {
      let seed = run + 101;
      const random = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
      const pick = <T,>(items: T[]) => items[(random() * items.length) | 0];
      let state: MeetingTranscript = EMPTY_MEETING_TRANSCRIPT;
      let clock = 0;
      const held: { rows: ReturnType<typeof meetingRows>; json: string }[] = [];
      const states: { state: MeetingTranscript; json: string }[] = [];
      for (let step = 0; step < 900; step++) {
        clock += random() * 2;
        const roll = random();
        if (roll < 0.9) {
          // The rep's mic often hears the call: the same words on both sides make echoes found later.
          const text = Array.from({ length: 1 + ((random() * 8) | 0) }, () => pick(WORDS)).join(" ") + (random() < 0.3 ? "." : "");
          const side = pick(["rep", "prospect"] as const);
          state = applyChannelResult(state, { text, isFinal: random() < 0.4, audioChannel: side, start: clock - random() * 3, end: clock + random() * 3 });
          if (random() < 0.2) state = applyChannelResult(state, { text, isFinal: true, audioChannel: side === "rep" ? "prospect" : "rep", start: clock, end: clock + 2 });
        } else if (roll < 0.95) {
          state = applyVoice(state, clock - random() * 2, 1 + ((random() * 2) | 0));
        }
        // Built incrementally, as on screen; checked against a build from scratch once the call is over.
        const rows = meetingRows(state);
        states.push({ state, json: JSON.stringify(rows.slice()) });
        if (step % 7 === 0) held.push({ rows, json: JSON.stringify(rows.slice()) });
      }
      for (const [index, { rows, json }] of held.entries()) assert.equal(JSON.stringify(rows.slice()), json, `run ${run}, held ${index}`);
      for (const [step, { state: at, json }] of states.entries()) {
        if (step % 3) continue;
        forgetFolds();
        assert.equal(json, JSON.stringify(meetingDisplayTurns(at)), `run ${run}, step ${step}`);
      }
      forgetFolds();
    }
  });
});
