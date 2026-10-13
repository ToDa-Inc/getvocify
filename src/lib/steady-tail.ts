import type { MeetingTranscript } from "./meeting-transcript";

type Side = "rep" | "prospect" | "unknown";
const SIDES: Side[] = ["rep", "prospect", "unknown"];

/** How long a word must stay the same in the live guess before it is shown (measured on real calls: ~0.5 s later). */
export const STEADY_MS = 500;
/** How long words already on screen wait for the guess that continues them, once their start has settled. */
const CARRY_MS = 1500;

type Track = {
  seen: number | undefined;
  /** The guess as last seen, and since when each of its words has had that form. */
  words: string[];
  since: number[];
  /** What is on screen of it. */
  shown: string[];
  /** Finals of this side when the guess was last seen: later ones settled (part of) it. */
  settled: number;
  at: number;
  /** Words shown past a final that settled their start, until the guess that continues them. */
  carried?: boolean;
};

const norm = (word: string) =>
  word.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^\p{L}\p{N}']/gu, "");
const toWords = (text: string) => text.split(/\s+/).filter(Boolean);
const sameWord = (a: string | undefined, b: string | undefined) => a !== undefined && b !== undefined && norm(a) === norm(b);

/** The shown words after the ones `final` settled, when `final` is how they start; null when it changed them. */
function after(shown: string[], final: string): string[] | null {
  const settled = toWords(final).map(norm).filter(Boolean);
  let matched = 0;
  let index = 0;
  for (; index < shown.length && matched < settled.length; index++) {
    const word = norm(shown[index]);
    if (!word) continue;
    if (word !== settled[matched]) return null;
    matched += 1;
  }
  return matched === settled.length ? shown.slice(index) : null;
}

/**
 * The words still being transcribed, the way a reader can follow them. The live guess rewrites its last words several
 * times a second; on screen a word only appears once it has kept its form for `STEADY_MS` (a new line's bubble with its
 * first steady word), and a shown word is never
 * taken back while the guess changes its mind: the final for those words replaces them, once. Only what the island
 * draws goes through here; the transcript, the memo and live help keep the guess as it is.
 */
export class SteadyTails {
  private tracks: Partial<Record<Side, Track>> = {};
  private readonly steadyMs: number;

  constructor(steadyMs: number = STEADY_MS) {
    this.steadyMs = steadyMs;
  }

  /** Whether words are waiting to be shown (only then does the island need drawing again without news). */
  waiting(): boolean {
    return Object.values(this.tracks).some((track) => track && (track.words.length > track.shown.length || track.carried));
  }

  /** The transcript as the island should draw it at `now` (ms, any steady clock). */
  view(state: MeetingTranscript, now: number): MeetingTranscript {
    const interims: MeetingTranscript["interims"] = {};
    for (const side of SIDES) {
      const finals = state.segments.filter((segment) => (segment.speaker ?? "unknown") === side);
      const guess = state.interims[side];
      let track = this.tracks[side];
      // Words on screen whose start a final just settled: the rest of them, until the guess that continues them.
      const carried = track && finals.length > track.settled
        ? after(track.shown, finals.slice(track.settled).map((segment) => segment.text).join(" "))
        : null;
      if (!guess) {
        if (track && carried?.length && now - track.at <= CARRY_MS) {
          track.carried = true;
          interims[side] = carried.join(" ");
        } else delete this.tracks[side];
        continue;
      }
      const words = toWords(guess);
      const seen = state.interimSeen?.[side];
      if (!track || track.seen !== seen || carried) {
        // A new guess: what was already shown of it (carried over a final) stays shown.
        const keep = carried ?? (track && track.seen === seen ? track.shown : []);
        track = { seen, words: [], since: [], shown: [], settled: finals.length, at: now };
        let k = 0;
        while (k < keep.length && sameWord(words[k], keep[k])) k++;
        track.words = words.slice(0, k);
        track.since = new Array(k).fill(-Infinity);
        track.shown = words.slice(0, k);
        this.tracks[side] = track;
      }
      const since = words.map((word, i) => (sameWord(track!.words[i], word) ? track!.since[i] : now));
      // A word is only as steady as everything before it.
      for (let i = 1; i < since.length; i++) since[i] = Math.max(since[i], since[i - 1]);
      let steady = 0;
      while (steady < words.length && now - since[steady] >= this.steadyMs) steady++;
      const agrees = track.shown.every((word, i) => sameWord(words[i], word));
      if (agrees) track.shown = words.slice(0, Math.max(steady, track.shown.length));
      // Disagreeing with what is shown: it stays as it is until the guess agrees again or its final arrives.
      track.words = words;
      track.since = since;
      track.settled = finals.length;
      track.at = now;
      // Nothing steady yet: no bubble until there is (the voice wave already shows someone is talking). The first
      // word is the most rewritten of all on real calls ("Oh." → "Hold" → "Hola,").
      if (track.shown.length) interims[side] = track.shown.join(" ");
    }
    return { ...state, interims };
  }
}
