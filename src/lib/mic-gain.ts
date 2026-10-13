/**
 * How loud a raw microphone is once the server has raised it. The desktop app's own microphone has no automatic gain (a
 * MacBook's peaks ~14x lower than the browser's), so the server raises it towards TARGET_PEAK by at most MAX_GAIN, from
 * its loudest recent sound (backend `echo_canceller.py`, same numbers). The page measures that same loudness for the
 * level meter and its checks; the audio it sends stays raw, which the server's echo removal needs.
 */

const TARGET_PEAK = 16000;
const MAX_GAIN = 8;
/** The loudest recent sound fades by half every this many seconds. */
const PEAK_HALF_LIFE_S = 10;
const SAMPLE_RATE = 16000;

export class MicGain {
  private loudest = TARGET_PEAK / MAX_GAIN;

  /** `samples` as the server will have them: raised, never above full scale. */
  apply(samples: Int16Array): Int16Array {
    let max = 0;
    for (let i = 0; i < samples.length; i++) max = Math.max(max, Math.abs(samples[i]));
    this.loudest = Math.max(max, this.loudest * 0.5 ** (samples.length / SAMPLE_RATE / PEAK_HALF_LIFE_S));
    const gain = Math.min(MAX_GAIN, Math.max(1, TARGET_PEAK / Math.max(this.loudest, 1)));
    if (gain === 1) return samples;
    const raised = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) raised[i] = Math.max(-32768, Math.min(32767, Math.round(samples[i] * gain)));
    return raised;
  }
}
