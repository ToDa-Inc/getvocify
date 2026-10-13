/**
 * Notices a recording whose audio isn't arriving, while it happens. A muted mic, the wrong input, or call audio macOS
 * won't hand over (Screen & System Audio Recording off) all arrive as a clean stream of zeros: nothing errors, so
 * nothing else would say so. A real mic always carries some noise, so pure zeros means nothing is flowing.
 */

export type AudioIssue = "mic" | "call" | null;

/** No sample above this (out of 32768) is digital silence, not a quiet room. */
export const SILENT_PEAK = 2;
/** The rep is talking: loud enough that the other side would normally answer within the wait. */
export const SPEAKING_PEAK = 1500;

export const MIC_SILENT_MS = 8_000;
/** The earliest the other side is called missing: a meeting's first half minute can be all the rep. */
export const CALL_SILENT_MS = 30_000;
/** And only once the rep has talked this long in total: someone was there to answer. */
export const CALL_TALKED_MS = 15_000;

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
  private startedAt: number;
  /** Any sound at all from the other side since the start: after that, their silence is just listening. */
  private themEverHeard = false;
  private youEverHeard = false;
  private talkedMs = 0;
  private lastSpokeAt: number | null = null;
  private readonly watchCall: boolean;

  /** `watchCall`: false when the other side's audio needs no permission (a Vocify call's own stream). */
  constructor(now: number, { watchCall }: { watchCall: boolean }) {
    this.soundAt = { you: now, them: now };
    this.startedAt = now;
    this.watchCall = watchCall;
  }

  /** One chunk as it arrived (for the mic, before echo removal: that can zero out a live mic). */
  hear(side: "you" | "them", samples: Int16Array, now: number): void {
    const loudest = peak(samples);
    if (loudest > SILENT_PEAK) {
      this.soundAt[side] = now;
      if (side === "them") this.themEverHeard = true;
      else this.youEverHeard = true;
    }
    if (side === "you" && loudest >= SPEAKING_PEAK) {
      // Time between two loud chunks counts as talking when they are close (a sentence, not two).
      if (this.lastSpokeAt !== null && now - this.lastSpokeAt < 1_000) this.talkedMs += now - this.lastSpokeAt;
      this.lastSpokeAt = now;
    }
  }

  /** After a pause: the silence while paused proves nothing. */
  restart(now: number): void {
    this.soundAt = { you: now, them: now };
    this.lastSpokeAt = null;
  }

  /** Any sound from this side since the start. */
  everHeard(side: "you" | "them"): boolean {
    return side === "you" ? this.youEverHeard : this.themEverHeard;
  }

  issue(now: number): AudioIssue {
    if (now - this.soundAt.you >= MIC_SILENT_MS) return "mic";
    // The other side listening is silence too (muted on Zoom is pure zeros), so a pitch must never trip this: only
    // call audio that has carried nothing since the start, after the rep has clearly been talking to someone.
    if (
      this.watchCall &&
      !this.themEverHeard &&
      now - this.startedAt >= CALL_SILENT_MS &&
      this.talkedMs >= CALL_TALKED_MS
    ) {
      return "call";
    }
    return null;
  }
}

/** What the rep is told, and which system page fixes it (Windows: its Sound settings for call audio). */
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
        title: "No sound from the other side yet",
        body: "If they have spoken, turn on Vocify in Screen & System Audio Recording, then relaunch Vocify.",
        settings: "systemAudio",
      }
    : {
        // Windows needs no permission for it: Vocify hears the default output, so the meeting app must play there.
        title: "No sound from the other side yet",
        body: "Vocify hears your default speaker or headset. Set Zoom or Teams to play through the same one.",
        settings: "systemAudio",
      };
}
