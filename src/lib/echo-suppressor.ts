/**
 * Keeps the call out of the rep's microphone.
 *
 * With speakers instead of headphones the microphone hears the call a moment after the call audio played, quieter and
 * smeared by the room, and the transcript then shows the other person as the rep. The browser's own echo cancellation
 * cannot help: it only knows the audio its own page plays, and the call plays in another app. The app does capture the
 * call's audio (the Windows loopback), so the suppressor compares the two.
 *
 * It works on loudness, not on waveforms: every 20 ms it keeps how loud each side was, finds the delay at which the
 * microphone's loudness follows the call's (`ECHO_CORRELATION` or better over the last 1.5 s) and how much quieter it
 * is, and mutes the 20 ms of microphone that is no louder than that echo. The rep's own voice is louder than the echo
 * and does not follow the call's loudness, so it passes, also while both talk. It fails open: when it is not sure, the
 * microphone is left as it is.
 *
 * Times come from the clock of the page (`endMs`, the moment the last sample of a chunk arrived), so the two audio
 * streams need not share a clock; the delay search covers what their paths add.
 */

export const SAMPLE_RATE = 16000;
/** Loudness is kept per hop. */
export const HOP_SAMPLES = 320;
const HOP_MS = (HOP_SAMPLES / SAMPLE_RATE) * 1000;

/** How far back the microphone's loudness is compared with the call's. */
const WINDOW_HOPS = 100;
/** The delays tried: the room, the speakers' and the capture's buffers, and the paths' arrival jitter. */
const MAX_LAG_HOPS = 50;
/**
 * A room smears what the speakers play: the echo is the call's loudness with a tail. The call's loudness is therefore
 * compared with a tail of its own, which falls by this much each hop (about 100 ms to fall by 10 dB).
 */
const TAIL_DECAY = 0.8;
/** Hops kept of each side's loudness (about 41 s). */
const KEEP_HOPS = 2048;
/** Quieter than this (amplitude, 16-bit) is room noise: never worth muting and never an echo's evidence. */
const FLOOR = 25;

/** How closely the microphone's loudness must follow the call's before anything is muted. */
export const ECHO_CORRELATION = 0.7;
/** The microphone may be this much louder than the echo it predicts before the extra counts as the rep's voice. */
export const VOICE_OVER_ECHO = 1.8;
/**
 * Echo has one delay and keeps it; two unrelated voices sometimes line up for a moment at a different delay each time.
 * A hop is only muted when, among the `STABLE_OF` hops up to it, at least `STABLE_NEEDED` found a good match at about
 * this hop's delay (pauses in the microphone have nothing to match and simply do not count).
 */
const STABLE_OF = 80;
const STABLE_NEEDED = 24;
const STABLE_LAG_TOLERANCE = 2;
/** The correlation a hop's best delay needs to count towards that. */
const STABLE_CORRELATION = 0.6;
/** A hop is only muted once the window holds this many hops where the call is audible. */
const MIN_CALL_HOPS = 12;

export type EchoStats = { hops: number; muted: number };

/** One hop's evidence, for tuning against recordings (never used in the app). */
export type EchoTrace = { hop: number; level: number; lag: number; correlation: number; gain: number; call: number };

export class EchoSuppressor {
  /** Receives each judged hop's evidence when set. */
  trace: ((entry: EchoTrace) => void) | null = null;
  private readonly correlation: number;
  private readonly voiceOverEcho: number;

  constructor(options: { correlation?: number; voiceOverEcho?: number } = {}) {
    this.correlation = options.correlation ?? ECHO_CORRELATION;
    this.voiceOverEcho = options.voiceOverEcho ?? VOICE_OVER_ECHO;
  }
  /** The call's loudness with the room's tail (see TAIL_DECAY). */
  private readonly call = new Float32Array(KEEP_HOPS);
  private readonly mic = new Float32Array(KEEP_HOPS);
  /** The best delay and its correlation found for each microphone hop, for the stability check. */
  private readonly lagAt = new Int16Array(KEEP_HOPS).fill(-1);
  private readonly correlationAt = new Float32Array(KEEP_HOPS);
  /** The absolute hop index each side has filled up to (exclusive). */
  private callEnd = 0;
  private micEnd = 0;
  /** The page's clock at hop 0: the start of whichever side's first chunk came first, so both sides count alike. */
  private origin: number | null = null;
  private hops = 0;
  private muted = 0;

  /** What the call played, as it arrives: 16 kHz mono PCM16. */
  pushCall(pcm: Int16Array, endMs: number): void {
    this.callEnd = Math.max(this.callEnd, this.fill(this.call, pcm, endMs, this.callEnd, true).at(-1)! + 1);
  }

  /** The microphone's chunk, with the hops that are only the call's echo set to silence. Same length. */
  process(pcm: Int16Array, endMs: number): Int16Array {
    const indexes = this.fill(this.mic, pcm, endMs, this.micEnd, false);
    this.micEnd = Math.max(this.micEnd, indexes.at(-1)! + 1);
    const out = pcm.slice();
    indexes.forEach((hop, j) => {
      this.hops += 1;
      if (!this.isEcho(hop)) return;
      this.muted += 1;
      out.fill(0, j * HOP_SAMPLES, Math.min(out.length, (j + 1) * HOP_SAMPLES));
    });
    return out;
  }

  stats(): EchoStats {
    return { hops: this.hops, muted: this.muted };
  }

  /**
   * Adds the chunk's loudness, one value per 20 ms of it (the last may be shorter), each placed by when it happened on
   * the page's clock so both sides' hop numbers are comparable (a chunk's first sample is `endMs` minus its length).
   * A gap (a stalled page) is silence. Returns the hop number of each of the chunk's hops.
   */
  private fill(target: Float32Array, pcm: Int16Array, endMs: number, filled: number, withTail: boolean): number[] {
    const startMs = endMs - (pcm.length / SAMPLE_RATE) * 1000;
    this.origin ??= startMs;
    const put = (hop: number, level: number) => {
      const before = target[(hop - 1 + KEEP_HOPS) % KEEP_HOPS];
      const tailed = withTail && hop > 0 ? Math.max(level, TAIL_DECAY * before) : level;
      target[hop % KEEP_HOPS] = Math.max(tailed, hop < filled ? target[hop % KEEP_HOPS] * 0 : 0);
    };
    const indexes: number[] = [];
    let next = filled;
    for (let from = 0; from < pcm.length; from += HOP_SAMPLES) {
      const to = Math.min(pcm.length, from + HOP_SAMPLES);
      let sum = 0;
      for (let i = from; i < to; i++) sum += pcm[i] * pcm[i];
      const hop = Math.max(0, Math.round((startMs + (from / SAMPLE_RATE) * 1000 - this.origin) / HOP_MS));
      // Hops the page never delivered are silence.
      for (let gap = next; gap < hop; gap++) put(gap, 0);
      put(hop, Math.sqrt(sum / (to - from)));
      indexes.push(hop);
      next = Math.max(next, hop + 1);
    }
    return indexes;
  }

  /** Whether the microphone's hop is the call's echo and nothing the rep said. */
  private isEcho(hop: number): boolean {
    const level = this.mic[hop % KEEP_HOPS];
    this.lagAt[hop % KEEP_HOPS] = -1;
    this.correlationAt[hop % KEEP_HOPS] = 0;
    if (level < FLOOR) return false;
    // The window and its delays must lie within what is still kept of the call.
    const from = hop - WINDOW_HOPS + 1;
    if (from - MAX_LAG_HOPS < 0 || from - MAX_LAG_HOPS < this.callEnd - KEEP_HOPS) return false;

    let bestLag = -1;
    let bestCorrelation = 0;
    let bestGain = 0;
    for (let lag = 0; lag <= MAX_LAG_HOPS; lag++) {
      let callHops = 0;
      let sumM = 0;
      let sumC = 0;
      let sumMM = 0;
      let sumCC = 0;
      let sumMC = 0;
      for (let h = from; h <= hop; h++) {
        const m = this.mic[h % KEEP_HOPS];
        const at = h - lag;
        const c = at < 0 || at >= this.callEnd ? 0 : this.call[at % KEEP_HOPS];
        if (c >= FLOOR) callHops += 1;
        sumM += m;
        sumC += c;
        sumMM += m * m;
        sumCC += c * c;
        sumMC += m * c;
      }
      if (callHops < MIN_CALL_HOPS) continue;
      const n = WINDOW_HOPS;
      const cov = sumMC - (sumM * sumC) / n;
      const varM = sumMM - (sumM * sumM) / n;
      const varC = sumCC - (sumC * sumC) / n;
      if (varM <= 0 || varC <= 0) continue;
      const correlation = cov / Math.sqrt(varM * varC);
      if (correlation > bestCorrelation) {
        bestCorrelation = correlation;
        bestLag = lag;
        // How loud the microphone is per unit of call: least squares through the origin.
        bestGain = sumCC > 0 ? sumMC / sumCC : 0;
      }
    }
    const at = hop - bestLag;
    const call = bestLag < 0 || at < 0 || at >= this.callEnd ? 0 : this.call[at % KEEP_HOPS];
    this.trace?.({ hop, level, lag: bestLag, correlation: bestCorrelation, gain: bestGain, call });
    this.lagAt[hop % KEEP_HOPS] = bestLag;
    this.correlationAt[hop % KEEP_HOPS] = bestCorrelation;
    if (bestLag < 0 || bestCorrelation < this.correlation) return false;
    let stable = 0;
    for (let h = hop - STABLE_OF + 1; h <= hop; h++) {
      if (h < 0) continue;
      const lag = this.lagAt[h % KEEP_HOPS];
      if (this.correlationAt[h % KEEP_HOPS] >= STABLE_CORRELATION && Math.abs(lag - bestLag) <= STABLE_LAG_TOLERANCE) stable += 1;
    }
    if (stable < STABLE_NEEDED) return false;
    if (call < FLOOR) return false;
    return level <= this.voiceOverEcho * bestGain * call;
  }
}
