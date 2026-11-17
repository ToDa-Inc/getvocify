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

describe("speaker timeline over a long call", () => {
  /** The rule as it was, over every sample: what the timeline must still answer. */
  function naive(samples: { at: number; names: string[] }[], start: number, end: number): string | null {
    const time = new Map<string, number>();
    samples.forEach((sample, index) => {
      const next = samples[index + 1]?.at ?? sample.at + 1;
      const from = Math.max(sample.at, start - 0.3);
      const to = Math.min(Math.min(next, sample.at + 1), end + 0.3);
      if (to <= from) return;
      for (const name of sample.names) time.set(name, (time.get(name) ?? 0) + to - from);
    });
    const [top, second] = [...time.entries()].sort((a, b) => b[1] - a[1]);
    if (!top || top[1] < 0.25) return null;
    if (second && top[1] - second[1] < 0.2 && top[1] < second[1] * 1.5) return null;
    return top[0];
  }

  it("names every recent sentence as reading all of it would, and keeps only the last minutes", () => {
    let seed = 5;
    const random = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
    const timeline = new SpeakerTimeline();
    const kept: { at: number; names: string[] }[] = [];
    let at = 0;
    for (let i = 0; i < 20000; i++) {
      at += 0.2 + random() * 0.6;
      const names = random() < 0.1 ? [] : random() < 0.5 ? ["Marta"] : random() < 0.8 ? ["Juan"] : ["Juan", "Marta"];
      const sorted = [...new Set(names)].sort();
      const last = kept.at(-1);
      if (!(last && last.names.join("\n") === sorted.join("\n") && at - last.at < 1)) kept.push({ at, names: sorted });
      timeline.record(at, names);
      if (i % 50 === 0) {
        const start = at - random() * 60;
        const end = start + random() * 8;
        assert.equal(timeline.name(start, end), naive(kept, start, end), `at ${at.toFixed(1)}`);
      }
    }
    const held = (timeline as unknown as { samples: unknown[] }).samples.length;
    assert.ok(held < 300 * 2 + 64, `${held} samples held after ${Math.round(at)} s`);
  });
});
