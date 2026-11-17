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
