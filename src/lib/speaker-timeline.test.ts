import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { SpeakerTimeline } from "./speaker-timeline.ts";

// Same cases as the Mac app (VocifyCoreChecks), so both name the other side alike.
describe("speaker timeline", () => {
  it("names a sentence by who was shown speaking for most of it", () => {
    const shown = new SpeakerTimeline();
    shown.record(0, ["Marta"]);
    shown.record(4, ["Juan"]);
    shown.record(6, []);
    assert.equal(shown.name(0.5, 3.5), "Marta");
    assert.equal(shown.name(3.5, 5.8), "Juan");
    assert.equal(shown.name(8, 9), null);
  });

  it("a close race names nobody; a clear lead still names", () => {
    const crosstalk = new SpeakerTimeline();
    crosstalk.record(10, ["Marta"]);
    crosstalk.record(10.5, ["Juan"]);
    crosstalk.record(11, []);
    assert.equal(crosstalk.name(10.3, 10.7), null);
    assert.equal(crosstalk.name(9.6, 10.4), "Marta");
  });

  it("a glimpse is not enough, and nothing recorded names nobody", () => {
    const glimpse = new SpeakerTimeline();
    assert.equal(glimpse.isEmpty, true);
    glimpse.record(20, ["Marta"]);
    glimpse.record(20.1, []);
    assert.equal(glimpse.name(20, 21), null);
  });
});
