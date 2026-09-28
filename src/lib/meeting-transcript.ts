export type MeetingSpeaker = "rep" | "prospect";

type SpeakerKey = MeetingSpeaker | "unknown";

export type MeetingTurn = { speaker: MeetingSpeaker | null; text: string };

/** One final from one channel, with its spoken time (seconds since the stream began) when known. */
export type MeetingSegment = {
  speaker: MeetingSpeaker | null;
  text: string;
  start: number | null;
  end: number | null;
};

/** Finals in arrival order; each channel keeps its own in-progress tail. */
export type MeetingTranscript = {
  segments: MeetingSegment[];
  interims: Partial<Record<SpeakerKey, string>>;
};

export type MeetingDisplayTurn = {
  key: string;
  speaker: MeetingSpeaker | null;
  label: string | null;
  text: string;
  pending: string;
};

export const EMPTY_MEETING_TRANSCRIPT: MeetingTranscript = { segments: [], interims: {} };

const SPEAKER_LABEL: Record<MeetingSpeaker, string> = { rep: "You", prospect: "Them" };
/** Same ids the memo review and extension use: S1 is always the rep. */
const SPEAKER_ID: Record<MeetingSpeaker, string> = { rep: "S1", prospect: "S2" };
const SPEAKER_ORDER: SpeakerKey[] = ["rep", "prospect", "unknown"];
/** How far apart two channels' words can be and still be the same sound (mic hearing the speakers). */
const ECHO_WINDOW_S = 1.5;
/** Share of a mic segment's words that must also be in the meeting audio to count as echo. */
const ECHO_OVERLAP = 0.6;

function speakerOf(channel: unknown): MeetingSpeaker | null {
  return channel === "rep" || channel === "prospect" ? channel : null;
}

function keyOf(speaker: MeetingSpeaker | null): SpeakerKey {
  return speaker ?? "unknown";
}

function speakerFromKey(key: SpeakerKey): MeetingSpeaker | null {
  return key === "unknown" ? null : key;
}

function seconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Joins streamed chunks so "hola" + ", qué tal" reads "hola, qué tal". */
export function joinChunks(left: string, right: string): string {
  if (!left) return right;
  if (!right) return left;
  return /^[,.;:!?…)]/.test(right) ? `${left}${right}` : `${left} ${right}`;
}

/** Reads a stored transcript, including drafts saved before segments existed. */
export function normalizeMeetingTranscript(raw: unknown): MeetingTranscript {
  const value = (raw ?? {}) as { segments?: MeetingSegment[]; turns?: MeetingTurn[]; interims?: MeetingTranscript["interims"] };
  const segments = Array.isArray(value.segments)
    ? value.segments
    : (value.turns ?? []).map((turn) => ({ speaker: turn.speaker, text: turn.text, start: null, end: null }));
  return { segments, interims: value.interims ?? {} };
}

export function applyChannelResult(
  state: MeetingTranscript,
  result: { text: string; isFinal: boolean; audioChannel?: unknown; start?: unknown; end?: unknown },
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
  const start = seconds(result.start);
  const segment = { speaker, text, start, end: seconds(result.end) ?? start };
  const { [key]: _settled, ...interims } = state.interims;
  return { segments: [...state.segments, segment], interims };
}

/** Treats every in-progress tail as final, e.g. when the meeting stops mid-sentence. */
export function settleMeeting(state: MeetingTranscript): MeetingTranscript {
  return SPEAKER_ORDER.reduce<MeetingTranscript>((acc, key) => {
    const text = state.interims[key];
    return text
      ? applyChannelResult(acc, { text, isFinal: true, audioChannel: speakerFromKey(key) })
      : acc;
  }, { segments: state.segments, interims: {} });
}

function words(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .split(/[^\p{L}\p{N}']+/u)
    .filter(Boolean);
}

/**
 * The mic also hears the meeting through the speakers. A mic segment whose words
 * were said on the meeting audio at the same moment is that echo, not the rep.
 */
function isEcho(segment: MeetingSegment, meeting: MeetingSegment[]): boolean {
  if (segment.speaker !== "rep" || segment.start === null) return false;
  const own = words(segment.text);
  if (!own.length) return false;
  const heard = new Set<string>();
  for (const other of meeting) {
    if (other.start === null) continue;
    const otherEnd = other.end ?? other.start;
    if (other.start <= (segment.end ?? segment.start) + ECHO_WINDOW_S && otherEnd >= segment.start - ECHO_WINDOW_S) {
      words(other.text).forEach((word) => heard.add(word));
    }
  }
  if (!heard.size) return false;
  const shared = own.filter((word) => heard.has(word)).length;
  return own.length <= 2 ? shared === own.length : shared / own.length >= ECHO_OVERLAP;
}

const turnsCache = new WeakMap<MeetingSegment[], MeetingTurn[]>();

/**
 * Settled turns in the order they were spoken: segments sort by start time (untimed
 * ones keep their arrival slot), mic echo is dropped, and consecutive segments from
 * the same speaker read as one turn.
 */
export function meetingTurns(state: MeetingTranscript): MeetingTurn[] {
  const cached = turnsCache.get(state.segments);
  if (cached) return cached;
  let clock = 0;
  const timed = state.segments.map((segment, arrival) => {
    if (segment.start !== null) clock = segment.start;
    return { segment, at: clock, arrival };
  });
  timed.sort((a, b) => a.at - b.at || a.arrival - b.arrival);
  const meeting = state.segments.filter((segment) => segment.speaker === "prospect");
  const turns: MeetingTurn[] = [];
  for (const { segment } of timed) {
    if (isEcho(segment, meeting)) continue;
    const last = turns[turns.length - 1];
    if (last && (last.speaker === segment.speaker || segment.speaker === null)) {
      // A fragment without a channel continues whoever was talking.
      last.text = joinChunks(last.text, segment.text);
    } else if (last && last.speaker === null) {
      // An opening fragment without a channel belongs to the first labeled speaker.
      last.speaker = segment.speaker;
      last.text = joinChunks(last.text, segment.text);
    } else {
      turns.push({ speaker: segment.speaker, text: segment.text });
    }
  }
  turnsCache.set(state.segments, turns);
  return turns;
}

/**
 * Render-ready paragraphs keyed by position, so React keeps settled bubbles; a
 * pending tail joins its speaker's last paragraph when it continues it.
 */
export function meetingDisplayTurns(state: MeetingTranscript): MeetingDisplayTurn[] {
  const rows: MeetingDisplayTurn[] = meetingTurns(state).map((turn, index) => ({
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
  return state.segments.length > 0 || Object.values(state.interims).some(Boolean);
}

export function meetingUploadText(state: MeetingTranscript): string {
  return meetingTurns(settleMeeting(state))
    .map((turn) => (turn.speaker ? `SPEAKER: ${SPEAKER_ID[turn.speaker]}\n${turn.text}` : turn.text))
    .join("\n\n")
    .trim();
}

/**
 * The end of what someone is saying, trimmed at a sentence start when possible
 * and otherwise at a word, never mid-word. "…" marks that earlier words exist.
 */
export function phraseTail(text: string, maxChars: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= maxChars) return clean;
  const from = clean.length - maxChars;
  const sentenceStarts = [...clean.matchAll(/[.!?…]\s+(?=\S)/g)].map((m) => m.index! + m[0].length);
  const sentence = sentenceStarts.find((start) => start >= from);
  if (sentence !== undefined) return `…${clean.slice(sentence)}`;
  const word = clean.indexOf(" ", from);
  return word === -1 ? `…${clean.slice(from)}` : `…${clean.slice(word + 1)}`;
}

export function meetingLastLine(state: MeetingTranscript): string {
  const rows = meetingDisplayTurns(state);
  const last = rows[rows.length - 1];
  return last ? phraseTail(joinChunks(last.text, last.pending), 110) : "";
}

export type MeetingOverlayTurn = {
  key: string;
  you: boolean;
  label: string | null;
  text: string;
  pending: string;
};

/** What the floating pill shows: the live line, and the last few turns when opened. */
export function meetingOverlay(
  state: MeetingTranscript,
  { turns = 4, lineChars = 64, turnChars = 150 } = {},
): { line: string; lineLabel: string | null; recent: MeetingOverlayTurn[] } {
  const rows = meetingDisplayTurns(state);
  const last = rows[rows.length - 1];
  const recent = rows.slice(-turns).map((row) => {
    const full = phraseTail(joinChunks(row.text, row.pending), turnChars);
    // Keep the settled/pending split on the trimmed text so the tail stays styled.
    const pending = row.pending && full.endsWith(row.pending) ? row.pending : "";
    return {
      key: row.key,
      you: row.speaker === "rep",
      label: row.label,
      text: pending ? full.slice(0, full.length - pending.length).trimEnd() : full,
      pending,
    };
  });
  return {
    line: last ? phraseTail(joinChunks(last.text, last.pending), lineChars) : "",
    lineLabel: last?.label ?? null,
    recent,
  };
}
