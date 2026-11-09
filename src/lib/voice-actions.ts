import { mergeVoices, moveLines, renameVoice, type MeetingTranscript } from "./meeting-transcript.ts";

/** What the rep does to the voices of the other side: from the dashboard's transcript, or from the island as a `voice:` command. */
export type VoiceAction =
  | { op: "rename"; voice: number; name: string }
  | { op: "merge"; keep: number; drop: number }
  /** The lines (where each began) of one paragraph go to a voice, or to a new one when `voice` is null. */
  | { op: "move"; starts: number[]; voice: number | null };

export const VOICE_COMMAND = "voice:";
/** A name longer than this is not a name. */
const NAME_MAX = 60;

const isVoice = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 1;
const isStart = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** The island's `voice:{...}` command, or null when it is not one or is not well formed. */
export function parseVoiceCommand(command: string): VoiceAction | null {
  if (!command.startsWith(VOICE_COMMAND)) return null;
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(command.slice(VOICE_COMMAND.length));
  } catch {
    return null;
  }
  if (!raw || typeof raw !== "object") return null;
  if (raw.op === "rename" && isVoice(raw.voice) && typeof raw.name === "string") {
    return { op: "rename", voice: raw.voice, name: raw.name.trim().slice(0, NAME_MAX) };
  }
  if (raw.op === "merge" && isVoice(raw.keep) && isVoice(raw.drop) && raw.keep !== raw.drop) {
    return { op: "merge", keep: raw.keep, drop: raw.drop };
  }
  const { starts, voice } = raw;
  if (raw.op === "move" && Array.isArray(starts) && starts.length > 0 && starts.every(isStart) && (voice === null || isVoice(voice))) {
    return { op: "move", starts, voice: voice as number | null };
  }
  return null;
}

/** What it does to the transcript at once. A move to a new voice waits for the backend, which says which voice it is. */
export function applyVoiceAction(state: MeetingTranscript, action: VoiceAction): MeetingTranscript {
  if (action.op === "rename") return renameVoice(state, action.voice, action.name.slice(0, NAME_MAX));
  if (action.op === "merge") return mergeVoices(state, action.keep, action.drop);
  return action.voice === null ? state : moveLines(state, action.starts, action.voice);
}

/** What the backend needs to know to learn from it (names stay on this side). */
export function voiceMessage(action: VoiceAction): Record<string, unknown> | null {
  if (action.op === "merge") return { type: "VoiceMerge", keep: action.keep, drop: action.drop };
  if (action.op === "move") return { type: "VoiceMove", starts: action.starts, voice: action.voice };
  return null;
}
