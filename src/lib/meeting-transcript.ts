export type MeetingSpeaker = "rep" | "prospect";

type SpeakerKey = MeetingSpeaker | "unknown";

export type MeetingTurn = { speaker: MeetingSpeaker | null; text: string };

/** Finals are settled turns; each channel keeps its own in-progress tail. */
export type MeetingTranscript = {
  turns: MeetingTurn[];
  interims: Partial<Record<SpeakerKey, string>>;
};

export type MeetingDisplayTurn = {
  key: string;
  speaker: MeetingSpeaker | null;
  label: string | null;
  text: string;
  pending: string;
};

export const EMPTY_MEETING_TRANSCRIPT: MeetingTranscript = { turns: [], interims: {} };

const SPEAKER_LABEL: Record<MeetingSpeaker, string> = { rep: "You", prospect: "Them" };
const SPEAKER_ORDER: SpeakerKey[] = ["rep", "prospect", "unknown"];

function speakerOf(channel: unknown): MeetingSpeaker | null {
  return channel === "rep" || channel === "prospect" ? channel : null;
}

function keyOf(speaker: MeetingSpeaker | null): SpeakerKey {
  return speaker ?? "unknown";
}

function speakerFromKey(key: SpeakerKey): MeetingSpeaker | null {
  return key === "unknown" ? null : key;
}

/** Joins streamed chunks so "hola" + ", qué tal" reads "hola, qué tal". */
export function joinChunks(left: string, right: string): string {
  if (!left) return right;
  if (!right) return left;
  return /^[,.;:!?…)]/.test(right) ? `${left}${right}` : `${left} ${right}`;
}

/** Consecutive finals from the same speaker join into one paragraph. */
export function applyChannelResult(
  state: MeetingTranscript,
  result: { text: string; isFinal: boolean; audioChannel?: unknown },
): MeetingTranscript {
  const text = result.text.trim();
  const speaker = speakerOf(result.audioChannel);
  const key = keyOf(speaker);
  if (!text) {
    // An empty final closes that channel's utterance; an empty interim changes nothing.
    if (!result.isFinal || !state.interims[key]) return state;
    const { [key]: _closed, ...interims } = state.interims;
    return { ...state, interims };
  }
  if (!result.isFinal) {
    if (state.interims[key] === text) return state;
    return { ...state, interims: { ...state.interims, [key]: text } };
  }

  const turns = [...state.turns];
  const last = turns[turns.length - 1];
  if (last && last.speaker === speaker) {
    turns[turns.length - 1] = { speaker, text: joinChunks(last.text, text) };
  } else {
    turns.push({ speaker, text });
  }
  const { [key]: _settled, ...interims } = state.interims;
  return { turns, interims };
}

/** Treats every in-progress tail as final, e.g. when the meeting stops mid-sentence. */
export function settleMeeting(state: MeetingTranscript): MeetingTranscript {
  return SPEAKER_ORDER.reduce<MeetingTranscript>((acc, key) => {
    const text = state.interims[key];
    return text
      ? applyChannelResult(acc, { text, isFinal: true, audioChannel: speakerFromKey(key) })
      : acc;
  }, { turns: state.turns, interims: {} });
}

/**
 * Stable, render-ready paragraphs. Settled turns keep their index as key, so React
 * never rebuilds them; a pending tail joins its speaker's last paragraph when it
 * continues it, otherwise it takes the key the paragraph will keep once final.
 */
export function meetingDisplayTurns(state: MeetingTranscript): MeetingDisplayTurn[] {
  const rows: MeetingDisplayTurn[] = state.turns.map((turn, index) => ({
    key: String(index),
    speaker: turn.speaker,
    label: turn.speaker ? SPEAKER_LABEL[turn.speaker] : null,
    text: turn.text,
    pending: "",
  }));
  const last = rows[rows.length - 1];
  for (const key of SPEAKER_ORDER) {
    const pending = state.interims[key];
    if (!pending) continue;
    const speaker = speakerFromKey(key);
    if (last && last.speaker === speaker && !last.pending) {
      last.pending = pending;
      continue;
    }
    rows.push({
      key: String(rows.length),
      speaker,
      label: speaker ? SPEAKER_LABEL[speaker] : null,
      text: "",
      pending,
    });
  }
  return rows;
}

export function meetingHasSpeech(state: MeetingTranscript): boolean {
  return state.turns.length > 0 || Object.values(state.interims).some(Boolean);
}

export function meetingUploadText(state: MeetingTranscript): string {
  return settleMeeting(state)
    .turns.map((turn) => (turn.speaker ? `${SPEAKER_LABEL[turn.speaker]}: ${turn.text}` : turn.text))
    .join("\n\n")
    .trim();
}

export function meetingLastLine(state: MeetingTranscript): string {
  const rows = meetingDisplayTurns(state);
  const last = rows[rows.length - 1];
  const text = last ? joinChunks(last.text, last.pending) : "";
  return text.length > 110 ? `…${text.slice(-110)}` : text;
}
