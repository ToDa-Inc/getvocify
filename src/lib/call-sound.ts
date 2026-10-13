/**
 * Loud enough to be someone speaking (RMS of 16-bit samples): the same line the backend draws before it sends a
 * side's audio to be transcribed (`SPEECH_RMS` in live_channel_sessions.py).
 */
const SPEECH_RMS = 100;
/** Sound older than this can no longer hold anything back (the echo check looks no further either). */
const KEEP_S = 30;

/**
 * When the call's own audio had sound, on the clock its transcript is timed by: the seconds of it sent so far.
 * The island holds back a rep line said while the call had sound until the call's words for that moment arrive.
 */
export class CallSound {
  heardS = 0;
  private spans: Array<[number, number]> = [];
  private readonly sampleRate: number;

  /** `sampleRate`: the rate the call's audio is sent at. */
  constructor(sampleRate: number) {
    this.sampleRate = sampleRate;
  }

  /** One chunk of the call's audio as it was sent (mono PCM16). */
  hear(pcm: Int16Array): void {
    const from = this.heardS;
    this.heardS += pcm.length / this.sampleRate;
    while (this.spans.length && this.spans[0][1] < this.heardS - KEEP_S) this.spans.shift();
    let sum = 0;
    for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i];
    if (!pcm.length || Math.sqrt(sum / pcm.length) < SPEECH_RMS) return;
    const last = this.spans[this.spans.length - 1];
    if (last && last[1] >= from - 1e-6) last[1] = this.heardS;
    else this.spans.push([from, this.heardS]);
  }

  audible(from: number, to: number): boolean {
    return this.spans.some(([start, end]) => start <= to && end >= from);
  }
}
