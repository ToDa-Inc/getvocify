/**
 * Who the meeting app showed as speaking, over the call's audio clock (seconds since the other
 * side's audio began). Read a few times a second by the desktop app (Zoom's screen, Google Meet
 * through the Vocify extension); a "Them" sentence is credited to whoever was shown speaking for
 * most of the time it was said. Same rules as SpeakerTimeline.swift in the Mac app.
 */
type Sample = { at: number; names: string[] };

/** A sample stands for this long when the next one is late. */
const SAMPLE_SPAN = 1;
const SLACK = 0.3;
/** A name needs this much time shown; a closer race than both limits names nobody. */
const MIN_SHOWN = 0.25;
const CLOSE_GAP = 0.2;
const CLEAR_LEAD = 1.5;

export class SpeakerTimeline {
  private samples: Sample[] = [];

  get isEmpty(): boolean {
    return this.samples.length === 0;
  }

  /** Records what the app shows now; repeats of the same speakers are folded. */
  record(at: number, names: string[]): void {
    const sorted = [...new Set(names)].sort();
    const last = this.samples.at(-1);
    if (last && last.names.join("\n") === sorted.join("\n") && at - last.at < SAMPLE_SPAN) return;
    this.samples.push({ at, names: sorted });
  }

  /** The person shown speaking for most of [start, end]; null when nobody was, or two were about as long ("Them" beats a wrong name). */
  name(start: number, end: number): string | null {
    const time = new Map<string, number>();
    this.samples.forEach((sample, index) => {
      const next = this.samples[index + 1]?.at ?? sample.at + SAMPLE_SPAN;
      const from = Math.max(sample.at, start - SLACK);
      const to = Math.min(Math.min(next, sample.at + SAMPLE_SPAN), end + SLACK);
      if (to <= from) return;
      for (const name of sample.names) time.set(name, (time.get(name) ?? 0) + to - from);
    });
    const ranked = [...time.entries()].sort((a, b) => b[1] - a[1]);
    const [top, second] = ranked;
    if (!top || top[1] < MIN_SHOWN) return null;
    if (second && top[1] - second[1] < CLOSE_GAP && top[1] < second[1] * CLEAR_LEAD) return null;
    return top[0];
  }
}
