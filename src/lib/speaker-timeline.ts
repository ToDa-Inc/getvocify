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
/**
 * How far back a sentence can start when its words come back: finals arrive seconds after they are said, and one long
 * sentence can run for a minute or two. Five minutes leaves room for both; the call can last hours.
 */
const KEEP_S = 300;
/** Old samples go this many at a time, not one by one. */
const TRIM_BATCH = 64;

export class SpeakerTimeline {
  /** By time. Only the last KEEP_S are kept: a sentence is named when its words come back, never later than that. */
  private samples: Sample[] = [];

  get isEmpty(): boolean {
    return this.samples.length === 0;
  }

  /** Records what the app shows now; repeats of the same speakers are folded. */
  record(at: number, names: string[]): void {
    const sorted = [...new Set(names)].sort();
    const last = this.samples.at(-1);
    if (last && last.names.join("\n") === sorted.join("\n") && at - last.at < SAMPLE_SPAN) return;
    if (!last || at >= last.at) this.samples.push({ at, names: sorted });
    else this.samples.splice(this.firstFrom(at + Number.EPSILON), 0, { at, names: sorted });
    // Read a few times a second for the whole call: what is older than any sentence still to come goes, in batches.
    const stale = this.firstFrom(this.samples[this.samples.length - 1].at - KEEP_S);
    if (stale >= TRIM_BATCH) this.samples.splice(0, stale);
  }

  /** The first sample at or after `at`. */
  private firstFrom(at: number): number {
    let low = 0;
    let high = this.samples.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (this.samples[middle].at < at) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  /** The person shown speaking for most of [start, end]; null when nobody was, or two were about as long ("Them" beats a wrong name). */
  name(start: number, end: number): string | null {
    const time = new Map<string, number>();
    // A sample stands for at most SAMPLE_SPAN: only the ones from just before the sentence on can count.
    for (let index = this.firstFrom(start - SLACK - SAMPLE_SPAN); index < this.samples.length; index++) {
      const sample = this.samples[index];
      if (sample.at >= end + SLACK) break;
      const next = this.samples[index + 1]?.at ?? sample.at + SAMPLE_SPAN;
      const from = Math.max(sample.at, start - SLACK);
      const to = Math.min(Math.min(next, sample.at + SAMPLE_SPAN), end + SLACK);
      if (to <= from) continue;
      for (const name of sample.names) time.set(name, (time.get(name) ?? 0) + to - from);
    }
    const ranked = [...time.entries()].sort((a, b) => b[1] - a[1]);
    const [top, second] = ranked;
    if (!top || top[1] < MIN_SHOWN) return null;
    if (second && top[1] - second[1] < CLOSE_GAP && top[1] < second[1] * CLEAR_LEAD) return null;
    return top[0];
  }
}
