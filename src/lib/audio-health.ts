/**
 * Notices a recording whose audio isn't arriving, while it happens. A muted mic, the wrong input, or call audio macOS
 * won't hand over (Screen & System Audio Recording off) all arrive as a clean stream of zeros: nothing errors, so
 * nothing else would say so. A real mic always carries some noise, so pure zeros means nothing is flowing.
 */

export type AudioIssue = "mic" | "call" | null;

/** No sample above this (out of 32768) is digital silence, not a quiet room. */
export const SILENT_PEAK = 2;
/** The rep is talking: loud enough that the other side would normally answer within the wait. */
const SPEAKING_PEAK = 1500;

export const MIC_SILENT_MS = 8_000;
export const CALL_SILENT_MS = 30_000;

/** Loudness of one PCM16 chunk, eased so normal speech sits around 0.5. */
export function pcmLevel(pcm: ArrayBuffer): number {
  const samples = new Int16Array(pcm);
  let sum = 0;
  let count = 0;
  for (let i = 0; i < samples.length; i += 8) {
    const v = samples[i] / 32768;
    sum += v * v;
    count++;
  }
  const rms = count ? Math.sqrt(sum / count) : 0;
  return Math.min(1, Math.sqrt(rms * 6));
}

/** The loudest sample: above SILENT_PEAK, something is arriving. */
export function peak(samples: Int16Array): number {
  let max = 0;
  for (let i = 0; i < samples.length; i++) {
    const v = Math.abs(samples[i]);
    if (v > max) max = v;
  }
  return max;
}

export class AudioHealth {
  private soundAt: { you: number; them: number };
  private spokeAt = Number.NEGATIVE_INFINITY;
  private readonly watchCall: boolean;

  /** `watchCall`: false when the other side's audio needs no permission (a Vocify call's own stream). */
  constructor(now: number, { watchCall }: { watchCall: boolean }) {
    this.soundAt = { you: now, them: now };
    this.watchCall = watchCall;
  }

  /** One chunk as it arrived (for the mic, before echo removal: that can zero out a live mic). */
  hear(side: "you" | "them", samples: Int16Array, now: number): void {
    const loudest = peak(samples);
    if (loudest > SILENT_PEAK) this.soundAt[side] = now;
    if (side === "you" && loudest >= SPEAKING_PEAK) this.spokeAt = now;
  }

  /** After a pause: the silence while paused proves nothing. */
  restart(now: number): void {
    this.soundAt = { you: now, them: now };
    this.spokeAt = Number.NEGATIVE_INFINITY;
  }

  issue(now: number): AudioIssue {
    if (now - this.soundAt.you >= MIC_SILENT_MS) return "mic";
    // The other side being quiet is normal: only a rep who has been talking to nobody for the whole wait counts.
    if (this.watchCall && now - this.soundAt.them >= CALL_SILENT_MS && now - this.spokeAt < CALL_SILENT_MS) return "call";
    return null;
  }
}

/** What the rep is told, and which system setting fixes it (none where no permission is involved). */
export function audioIssueCopy(
  issue: Exclude<AudioIssue, null>,
  platform: "darwin" | "win32" | null,
): { title: string; body: string; settings: "microphone" | "systemAudio" | null } {
  if (issue === "mic") {
    return {
      title: "Your mic isn't sending audio",
      body: "Check it isn't muted and that the right input is selected.",
      settings: "microphone",
    };
  }
  return platform === "darwin"
    ? {
        title: "Vocify can't hear the other side",
        body: "Turn on Vocify in Screen & System Audio Recording, then relaunch Vocify.",
        settings: "systemAudio",
      }
    : {
        title: "Vocify can't hear the other side",
        body: "Check the call's sound plays on this computer.",
        settings: null,
      };
}
