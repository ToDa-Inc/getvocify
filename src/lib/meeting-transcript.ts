export type MeetingSpeaker = "rep" | "prospect";

type SpeakerKey = MeetingSpeaker | "unknown";

export type MeetingTurn = { speaker: MeetingSpeaker | null; text: string };

/** One final from one channel, with its spoken time (seconds since the stream began) when known. */
export type MeetingSegment = {
  speaker: MeetingSpeaker | null;
  text: string;
  start: number | null;
  end: number | null;
  /** When its words first showed on screen; the live transcript keeps this order so nothing moves. */
  seen?: number;
  /** Who on the other side said it, when the meeting app showed it (the Mac app reads it). */
  name?: string | null;
  /** Which voice on the other side said it (1, 2, ...): the backend tells voices apart by sound, a moment after the text. */
  voice?: number | null;
};

/** Finals in arrival order; each channel keeps its own in-progress tail. */
export type MeetingTranscript = {
  segments: MeetingSegment[];
  interims: Partial<Record<SpeakerKey, string>>;
  /** When each tail started, so a tail settled at stop still sorts where it was said. */
  interimStarts?: Partial<Record<SpeakerKey, number>>;
  /** When each tail first showed; its final keeps the same place and bubble. */
  interimSeen?: Partial<Record<SpeakerKey, number>>;
  /** Where each tail's audio reaches: a final ending before it leaves words still to come. */
  interimEnds?: Partial<Record<SpeakerKey, number>>;
  /** Next `seen` to hand out. */
  nextSeen?: number;
  /** What the rep called each voice on the other side; beats what the meeting app showed. */
  voiceNames?: Record<number, string>;
};

export type MeetingDisplayTurn = {
  key: string;
  speaker: MeetingSpeaker | null;
  label: string | null;
  text: string;
  pending: string;
  /** When the paragraph's first and latest words were said (seconds into the call). */
  start?: number | null;
  end?: number | null;
  /** The person on the other side, when the meeting app showed who was speaking. */
  name?: string | null;
  /** The voice that said it, when the backend told voices apart. */
  voice?: number | null;
  /** Where each of its settled lines began, to move the paragraph to another voice. */
  starts?: number[];
  /** Heard with the other side but said by a colleague of the rep (meeting-team.ts): its speaker is then the rep's side. */
  team?: boolean;
};

export const EMPTY_MEETING_TRANSCRIPT: MeetingTranscript = { segments: [], interims: {} };

const SPEAKER_LABEL: Record<MeetingSpeaker, string> = { rep: "You", prospect: "Them" };
const VOICE_LABEL = "Voice";

/**
 * A default name ("You", "Them", "Voice 2") in the rep's language, for the screens: what the meeting app showed and what
 * the rep typed stay as they are. The transcript keeps the English defaults so a rename compares and caches the same way.
 */
export function meetingLabelIn(label: string | null, language: "EN" | "ES"): string | null {
  if (language !== "ES" || label === null) return label;
  if (label === SPEAKER_LABEL.rep) return "Tú";
  if (label === SPEAKER_LABEL.prospect) return "Cliente";
  const voice = new RegExp(`^${VOICE_LABEL} (\\d+)$`).exec(label);
  return voice ? `Voz ${voice[1]}` : label;
}
/** A voice takes the name the meeting app showed for it when this many of its lines carried that name, and nearly all did. */
const LEARN_MIN_LINES = 2;
const LEARN_MIN_SHARE = 0.8;
/** Same ids the memo review and extension use: S1 is always the rep. */
const SPEAKER_ID: Record<MeetingSpeaker, string> = { rep: "S1", prospect: "S2" };
const SPEAKER_ORDER: SpeakerKey[] = ["rep", "prospect", "unknown"];
/** How far apart two channels' words can be and still be the same sound (mic hearing the speakers). */
const ECHO_WINDOW_S = 1.5;
/** Share of a mic segment's words that must also be in the meeting audio to count as echo. */
const ECHO_OVERLAP = 0.6;
/**
 * "Vale", "sí, sí": this short, said while the other person was still talking, it is a
 * reaction, not a turn. It keeps its own small bubble but doesn't cut their paragraph.
 */
const INTERJECTION_WORDS = 2;
const OVERLAP_SLACK_S = 0.5;
/**
 * Someone talking at length reads as paragraphs, not one bubble that keeps growing under the reader: the same
 * speaker starts a new one after a real pause, or once theirs is long and its sentence has ended.
 */
const PAUSE_SPLIT_S = 2.5;
const LONG_PARAGRAPH_WORDS = 45;

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
  const value = (raw ?? {}) as {
    segments?: MeetingSegment[];
    turns?: MeetingTurn[];
    interims?: MeetingTranscript["interims"];
    interimStarts?: MeetingTranscript["interimStarts"];
    interimSeen?: MeetingTranscript["interimSeen"];
    nextSeen?: number;
    voiceNames?: MeetingTranscript["voiceNames"];
  };
  const stored: MeetingSegment[] = Array.isArray(value.segments)
    ? value.segments
    : (value.turns ?? []).map((turn) => ({ speaker: turn.speaker, text: turn.text, start: null, end: null }));
  // Drafts saved before `seen` existed show in arrival order.
  const segments = stored.map((segment, index) => (typeof segment.seen === "number" ? segment : { ...segment, seen: index }));
  return {
    segments,
    interims: value.interims ?? {},
    interimStarts: value.interimStarts ?? {},
    interimSeen: value.interimSeen ?? {},
    nextSeen: typeof value.nextSeen === "number" ? value.nextSeen : segments.length + Object.keys(value.interims ?? {}).length,
    ...(value.voiceNames ? { voiceNames: value.voiceNames } : {}),
  };
}

function without<T extends object>(map: T | undefined, key: SpeakerKey): T {
  const { [key]: _dropped, ...rest } = (map ?? {}) as Record<string, unknown>;
  return rest as T;
}

export function applyChannelResult(
  state: MeetingTranscript,
  result: {
    text: string;
    isFinal: boolean;
    audioChannel?: unknown;
    start?: unknown;
    end?: unknown;
    /** Who on the other side said it, when the meeting app showed it (finals only). */
    name?: string | null;
  },
): MeetingTranscript {
  const text = result.text.trim();
  const speaker = speakerOf(result.audioChannel);
  const key = keyOf(speaker);
  if (!text) {
    // An empty final closes that channel's utterance; an empty interim changes nothing.
    if (!result.isFinal || !state.interims[key]) return state;
    return {
      ...state,
      interims: without(state.interims, key),
      interimStarts: without(state.interimStarts, key),
      interimSeen: without(state.interimSeen, key),
      interimEnds: without(state.interimEnds, key),
    };
  }
  const start = seconds(result.start);
  const nextSeen = state.nextSeen ?? state.segments.length;
  const openSeen = state.interimSeen?.[key];
  if (!result.isFinal) {
    if (state.interims[key] === text) return state;
    const interimStarts = start === null ? state.interimStarts : { ...state.interimStarts, [key]: start };
    const tailEnd = seconds(result.end);
    const interimEnds = tailEnd === null ? without(state.interimEnds, key) : { ...state.interimEnds, [key]: tailEnd };
    if (openSeen !== undefined) return { ...state, interims: { ...state.interims, [key]: text }, interimStarts, interimEnds };
    return {
      ...state,
      interims: { ...state.interims, [key]: text },
      interimStarts,
      interimEnds,
      interimSeen: { ...state.interimSeen, [key]: nextSeen },
      nextSeen: nextSeen + 1,
    };
  }
  const end = seconds(result.end) ?? start;
  const segment: MeetingSegment = { speaker, text, start, end, seen: openSeen ?? nextSeen, ...(result.name ? { name: result.name } : {}) };
  const tail = state.interims[key];
  const tailEnd = state.interimEnds?.[key];
  // Only when the tail's audio goes past the final's: then more is coming for those words
  // (Speechmatics settles part of a sentence). A final for the whole tail (Deepgram) that
  // dropped a word must not leave it on screen.
  const rest = tail && end !== null && tailEnd !== undefined && end < tailEnd - 0.05 ? tailRemainder(tail, text) : null;
  if (rest) {
    // The tail's words this final doesn't cover stay on screen, in the same bubble, until
    // the next partial replaces them: dropping them would blank the end for a moment.
    return {
      ...state,
      segments: [...state.segments, segment],
      interims: { ...state.interims, [key]: rest },
      interimStarts: end === null ? state.interimStarts : { ...state.interimStarts, [key]: end },
      nextSeen: openSeen === undefined ? nextSeen + 1 : nextSeen,
    };
  }
  return {
    segments: [...state.segments, segment],
    interims: without(state.interims, key),
    interimStarts: without(state.interimStarts, key),
    interimSeen: without(state.interimSeen, key),
    nextSeen: openSeen === undefined ? nextSeen + 1 : nextSeen,
    ...(state.voiceNames ? { voiceNames: state.voiceNames } : {}),
  };
}

/**
 * The words of a live tail its final doesn't cover yet: "a b c d" after the final "a b c" is
 * "d". Counted in words, as a final may punctuate or correct the same words.
 */
export function tailRemainder(tail: string, final: string): string | null {
  const covered = words(final).length;
  const pieces = tail.split(/\s+/).filter(Boolean);
  let counted = 0;
  for (let index = 0; index < pieces.length; index++) {
    if (counted >= covered) return pieces.slice(index).join(" ");
    counted += words(pieces[index]).length;
  }
  return null;
}

/**
 * One side restarted in its real language (e.g. Catalan) and is sending its words from
 * `from` again: drop what it had from there on, so nothing shows twice.
 */
export function resetChannel(state: MeetingTranscript, audioChannel: unknown, from: unknown): MeetingTranscript {
  const speaker = speakerOf(audioChannel);
  const at = seconds(from);
  if (!speaker || at === null) return state;
  const key = keyOf(speaker);
  const segments = state.segments.filter((segment) => segment.speaker !== speaker || (segment.start ?? -1) < at - 0.01);
  if (segments.length === state.segments.length && !state.interims[key]) return state;
  return {
    ...state,
    segments,
    interims: without(state.interims, key),
    interimStarts: without(state.interimStarts, key),
    interimSeen: without(state.interimSeen, key),
    interimEnds: without(state.interimEnds, key),
  };
}

/** Treats every in-progress tail as final, e.g. when the meeting stops mid-sentence. */
export function settleMeeting(state: MeetingTranscript): MeetingTranscript {
  return SPEAKER_ORDER.reduce<MeetingTranscript>((acc, key) => {
    const text = state.interims[key];
    return text
      ? applyChannelResult(
          { ...acc, interimSeen: { ...acc.interimSeen, [key]: state.interimSeen?.[key] ?? acc.nextSeen ?? acc.segments.length } },
          { text, isFinal: true, audioChannel: speakerFromKey(key), start: state.interimStarts?.[key] },
        )
      : acc;
  }, { ...state, interims: {}, interimStarts: {}, interimSeen: {}, interimEnds: {} });
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
/** Finals arrive a few seconds late at most: older call audio can't be heard by a new mic line. */
const ECHO_LOOKBACK_S = 30;

/** The call's timed sentences, by start: each echo check then looks only at its own moment. */
type MeetingAudio = MeetingSegment[];

/** Built once per segments array (one per final); an interim never rebuilds it. */
const meetingAudioCache = new WeakMap<MeetingSegment[], MeetingAudio>();

function meetingAudio(segments: MeetingSegment[]): MeetingAudio {
  if (fold?.segments === segments) return fold.audio;
  const cached = meetingAudioCache.get(segments);
  if (cached) return cached;
  const audio = segments
    .filter((segment) => segment.speaker === "prospect" && segment.start !== null)
    .sort((a, b) => (a.start as number) - (b.start as number));
  meetingAudioCache.set(segments, audio);
  return audio;
}

const wordsCache = new WeakMap<MeetingSegment, string[]>();

function segmentWords(segment: MeetingSegment): string[] {
  let cached = wordsCache.get(segment);
  if (!cached) {
    cached = words(segment.text);
    wordsCache.set(segment, cached);
  }
  return cached;
}

function isEcho(segment: MeetingSegment, meeting: MeetingAudio, live?: MeetingSegment): boolean {
  if (segment.speaker !== "rep" || segment.start === null) return false;
  const own = segmentWords(segment);
  if (!own.length) return false;
  const heard = new Set<string>();
  const until = (segment.end ?? segment.start) + ECHO_WINDOW_S;
  // The last call sentence starting by `until`, then back in time only as far as matters.
  let low = 0;
  let high = meeting.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((meeting[middle].start as number) <= until) low = middle + 1;
    else high = middle;
  }
  for (let index = low - 1; index >= 0; index--) {
    const other = meeting[index];
    const otherStart = other.start as number;
    if (otherStart < segment.start - ECHO_LOOKBACK_S) break;
    if ((other.end ?? otherStart) >= segment.start - ECHO_WINDOW_S) {
      segmentWords(other).forEach((word) => heard.add(word));
    }
  }
  // The call's words still being written (not in `meeting`): heard the same way when they fall in the same window.
  if (live && live.start !== null && live.start <= until && live.start >= segment.start - ECHO_LOOKBACK_S && (live.end ?? live.start) >= segment.start - ECHO_WINDOW_S) {
    segmentWords(live).forEach((word) => heard.add(word));
  }
  if (!heard.size) return false;
  const shared = own.filter((word) => heard.has(word)).length;
  return own.length <= 2 ? shared === own.length : shared / own.length >= ECHO_OVERLAP;
}

/** A turn keyed by the arrival of its first segment, so its bubble keeps its identity as text grows. */
type KeyedTurn = MeetingTurn & { key: string };

const turnsCache = new WeakMap<MeetingSegment[], KeyedTurn[]>();
const plainTurnsCache = new WeakMap<MeetingSegment[], MeetingTurn[]>();

/**
 * Settled turns in the order they were spoken: segments sort by start time (untimed
 * ones keep their arrival slot), mic echo is dropped, and consecutive segments from
 * the same speaker read as one turn.
 */
export function meetingTurns(state: MeetingTranscript): MeetingTurn[] {
  const cached = plainTurnsCache.get(state.segments);
  if (cached) return cached;
  const turns = keyedTurns(state).map(({ speaker, text }) => ({ speaker, text }));
  plainTurnsCache.set(state.segments, turns);
  return turns;
}

function keyedTurns(state: MeetingTranscript): KeyedTurn[] {
  const cached = turnsCache.get(state.segments);
  if (cached) return cached;
  let clock = 0;
  const timed = state.segments.map((segment, arrival) => {
    if (segment.start !== null) clock = segment.start;
    return { segment, at: clock, arrival };
  });
  timed.sort((a, b) => a.at - b.at || a.arrival - b.arrival);
  const meeting = meetingAudio(state.segments);
  const turns: KeyedTurn[] = [];
  for (const { segment, arrival } of timed) {
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
      turns.push({ key: `s${arrival}`, speaker: segment.speaker, text: segment.text });
    }
  }
  turnsCache.set(state.segments, turns);
  return turns;
}

/** The mic hearing the call while it's still being written: never shown as the rep. */
function isEchoTail(state: MeetingTranscript, key: SpeakerKey, pending: string): boolean {
  const start = state.interimStarts?.[key];
  if (key !== "rep" || start === undefined) return false;
  const live = state.interims.prospect;
  const liveStart = state.interimStarts?.prospect;
  // What the call says right now counts when it started around the same moment.
  const now = live && liveStart !== undefined ? { speaker: "prospect" as const, text: live, start: liveStart, end: start } : undefined;
  return isEcho({ speaker: "rep", text: pending, start, end: start }, meetingAudio(state.segments), now);
}

type DisplayItem = {
  seen: number;
  /** Where the line came in (the order of items with the same `seen`). */
  arrival?: number;
  speaker: MeetingSpeaker | null;
  text: string;
  pending: string;
  start: number | null;
  end: number | null;
  name?: string | null;
  voice?: number | null;
};

/**
 * The paragraph an item continues: the last one when it's the same speaker, or the one
 * before a short interjection the other side made while this speaker was still talking.
 */
function paragraphFor(item: DisplayItem, rows: MeetingDisplayTurn[]): number {
  const lastAt = rows.length - 1;
  const last = rows[lastAt];
  if (!last) return -1;
  // Another person on the same side (two guests) starts their own paragraph: told apart by the name the meeting app
  // showed, else by voice. A line with neither (a short "sí") goes with whoever was talking.
  const samePerson = (row: MeetingDisplayTurn) =>
    row.name && item.name ? row.name === item.name : row.voice != null && item.voice != null ? row.voice === item.voice : true;
  if (!last.pending && samePerson(last) && (last.speaker === item.speaker || item.speaker === null || last.speaker === null)) {
    return startsNewParagraph(last, item) ? -1 : lastAt;
  }
  const before = rows[lastAt - 1];
  if (!before || !item.speaker || before.speaker !== item.speaker || before.pending || !samePerson(before)) return -1;
  if (last.speaker === item.speaker || last.pending || words(last.text).length > INTERJECTION_WORDS) return -1;
  // Said during their paragraph: after it began and before it ended. Not just after it: a one-word answer that
  // comes right behind a question ("¿Qué CRM usáis?" "Salesforce.") is a turn, and the next question is a new bubble.
  const said = last.start;
  if (said == null || before.start == null || before.end == null) return -1;
  return said >= before.start - OVERLAP_SLACK_S && said < before.end ? lastAt - 1 : -1;
}

/** Decided from what is already settled in `row`, so a tail and the final that replaces it always agree. */
function startsNewParagraph(row: MeetingDisplayTurn, item: DisplayItem): boolean {
  if (!row.text || !item.speaker || row.speaker !== item.speaker) return false;
  if (item.start != null && row.end != null && item.start - row.end >= PAUSE_SPLIT_S) return true;
  return /[.!?…]$/.test(row.text) && words(row.text).length >= LONG_PARAGRAPH_WORDS;
}

// Keyed by the segments, and valid only for the names the rep gave the voices when they were built.
/** The rows after an item, as far as a refold needs them: the rows before the last two never change again. */
type Snapshot = { length: number; last: [MeetingDisplayTurn | undefined, MeetingDisplayTurn | undefined] };

/** `offset`: settled rows before `rows` (the array always holds the last two whenever there are any before it). */
function snapshotOf(rows: MeetingDisplayTurn[], offset: number): Snapshot {
  const n = rows.length;
  return { length: offset + n, last: [rows[n - 2], rows[n - 1]] };
}

/**
 * Builds rows in the order words first showed on screen, never re-sorting what is already there: a bubble keeps its
 * place and key from its first word to its final. A row is copied before it changes, so a row another call holds (a
 * snapshot, or the rows on screen) never changes under it. `snaps` gets the rows after each item.
 */
function displayRows(items: DisplayItem[], rows: MeetingDisplayTurn[], manyVoices = false, snaps?: Snapshot[], offset = 0): MeetingDisplayTurn[] {
  const labelOf = (item: DisplayItem) =>
    item.name || (item.voice != null && manyVoices ? `${VOICE_LABEL} ${item.voice}` : item.speaker ? SPEAKER_LABEL[item.speaker] : null);
  for (const item of items) {
    const at = paragraphFor(item, rows);
    if (at !== -1) {
      rows[at] = { ...rows[at] };
      const row = rows[at];
      // A fragment without a channel continues whoever was talking; an opening one goes to the first speaker.
      if (row.speaker === null && item.speaker) {
        row.speaker = item.speaker;
        row.label = SPEAKER_LABEL[item.speaker];
      }
      if (item.pending) row.pending = item.pending;
      else row.text = joinChunks(row.text, item.text);
      row.start ??= item.start;
      if (!row.name && item.name) {
        row.name = item.name;
        row.label = item.name;
      }
      if (row.voice == null && item.voice != null) {
        row.voice = item.voice;
        if (!row.name) row.label = labelOf(item);
      }
      if (!item.pending && item.speaker === "prospect" && item.start != null) row.starts = [...(row.starts ?? []), item.start];
      if (item.end != null) row.end = Math.max(row.end ?? item.end, item.end);
    } else {
      rows.push({
        key: `u${item.seen}`,
        speaker: item.speaker,
        label: manyVoices && item.speaker === "prospect" && item.voice == null && !item.name ? lastVoiceLabel(rows) ?? labelOf(item) : labelOf(item),
        text: item.text,
        pending: item.pending,
        start: item.start,
        end: item.end,
        name: item.name ?? null,
        voice: item.voice ?? null,
        starts: !item.pending && item.speaker === "prospect" && item.start != null ? [item.start] : [],
      });
    }
    snaps?.push(snapshotOf(rows, offset));
  }
  return rows;
}

/**
 * The label of the last line of the other side that has its voice. A line too short to hold a voice (or whose voice is
 * still coming) reads as that person, not as a third "Them" beside "Voice 1" and "Voice 2".
 */
function lastVoiceLabel(rows: MeetingDisplayTurn[]): string | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    if (rows[i].speaker === "prospect" && rows[i].voice != null) return rows[i].label;
  }
  return null;
}

/** Who said each voice's lines, as the meeting app named them: a tally, kept as the lines arrive. */
type Tally = Map<number, Map<string, number>>;

function tallyLine(tally: Tally, segment: MeetingSegment): void {
  if (segment.speaker !== "prospect" || segment.voice == null || !segment.name) return;
  const names = tally.get(segment.voice) ?? new Map<string, number>();
  names.set(segment.name, (names.get(segment.name) ?? 0) + 1);
  tally.set(segment.voice, names);
}

/** A voice takes the name the meeting app showed for it when this many of its lines carried that name, and nearly all did. */
function learnedFrom(tally: Tally): Record<number, string> {
  const learned: Record<number, string> = {};
  for (const [voice, names] of tally) {
    const total = [...names.values()].reduce((sum, n) => sum + n, 0);
    const [name, lines] = [...names.entries()].sort((a, b) => b[1] - a[1])[0];
    if (lines >= LEARN_MIN_LINES && lines / total >= LEARN_MIN_SHARE) learned[voice] = name;
  }
  return learned;
}

/** Who a line is, by the rep's word first, then by the meeting app, then by what the app showed for its voice. */
function nameOf(segment: MeetingSegment, names: MeetingTranscript["voiceNames"], learned: Record<number, string>): string | null {
  const voice = segment.voice;
  return (voice != null ? names?.[voice] : undefined) || segment.name || (voice != null ? learned[voice] : undefined) || null;
}

function itemOf(segment: MeetingSegment, arrival: number, names: MeetingTranscript["voiceNames"], learned: Record<number, string>): DisplayItem {
  return {
    seen: segment.seen ?? arrival,
    arrival,
    speaker: segment.speaker,
    text: segment.text,
    pending: "",
    start: segment.start,
    end: segment.end,
    name: nameOf(segment, names, learned),
    voice: segment.voice ?? null,
  };
}

/** A list of rows read by index: an array is one, and so are `DisplayRows`. */
export type RowList<T> = {
  readonly length: number;
  at(index: number): T | undefined;
  slice(start?: number, end?: number): T[];
  /**
   * Rows this list shares with every other list that has the same `key`: their first `length` (up to the shorter) are the
   * same objects. Comparing or summing two such lists skips those rows.
   */
  readonly shared?: { key: object; length: number };
};

/**
 * The rows on screen in two parts: the settled rows, in an array every later version of the call shares and that is only
 * ever appended to (each version reads its first `baseLength`), and the few rows after them that can still change. An
 * update builds only the second part, so it costs what changed, not the length of the call; reading the latest lines (the
 * screen's window, the island's changes, live help) never walks the rest.
 */
export class DisplayRows implements RowList<MeetingDisplayTurn> {
  readonly base: MeetingDisplayTurn[];
  readonly baseLength: number;
  readonly tail: MeetingDisplayTurn[];

  constructor(base: MeetingDisplayTurn[], baseLength: number, tail: MeetingDisplayTurn[]) {
    this.base = base;
    this.baseLength = baseLength;
    this.tail = tail;
  }

  get length(): number {
    return this.baseLength + this.tail.length;
  }

  get shared(): { key: object; length: number } {
    return { key: this.base, length: this.baseLength };
  }

  at(index: number): MeetingDisplayTurn | undefined {
    const i = index < 0 ? this.length + index : index;
    if (i < 0) return undefined;
    return i < this.baseLength ? this.base[i] : this.tail[i - this.baseLength];
  }

  slice(start = 0, end = this.length): MeetingDisplayTurn[] {
    const n = this.length;
    const from = Math.max(0, start < 0 ? n + start : Math.min(start, n));
    const to = Math.max(from, end < 0 ? n + end : Math.min(end, n));
    const out: MeetingDisplayTurn[] = new Array(to - from);
    for (let i = from; i < to; i++) out[i - from] = (i < this.baseLength ? this.base[i] : this.tail[i - this.baseLength]) as MeetingDisplayTurn;
    return out;
  }
}

/** How many leading rows two lists share as the same objects; settled rows two versions share are not walked. */
export function sharedRows<T>(a: RowList<T>, b: RowList<T>): number {
  const n = Math.min(a.length, b.length);
  if (a === b) return n;
  const left = a.shared;
  const right = b.shared;
  let i = left && right && left.key === right.key ? Math.min(left.length, right.length, n) : 0;
  while (i < n && a.at(i) === b.at(i)) i += 1;
  return i;
}

/**
 * The sum of `count` over a list. The part a list shares with others of its key is summed once and kept (in `memo`, one
 * per `count`): an update adds only the rows after it. `count` must give a row the same number every time.
 */
export function sumRows<T>(rows: RowList<T>, count: (row: T) => number, memo: WeakMap<object, number[]>): number {
  let from = 0;
  let total = 0;
  const shared = rows.shared;
  if (shared && shared.length > 0) {
    let sums = memo.get(shared.key);
    if (!sums) memo.set(shared.key, (sums = [0]));
    while (sums.length <= shared.length) sums.push(sums[sums.length - 1] + count(rows.at(sums.length - 1) as T));
    from = shared.length;
    total = sums[from];
  }
  for (let i = from; i < rows.length; i++) total += count(rows.at(i) as T);
  return total;
}

/**
 * Settled rows enter the shared array once this many rows follow them. A final changes the last row or two (an
 * interjection, a line placed before the other side's tail); an echo found later can reach further back, and then the
 * rows from there are copied once, as before.
 */
const SETTLE_AFTER = 12;

function settle(rows: DisplayRows): DisplayRows {
  const move = rows.tail.length - SETTLE_AFTER;
  if (move <= 0) return rows;
  // Another version read further into this array (the call changed below it): this one starts its own from its rows.
  const base = rows.baseLength === rows.base.length ? rows.base : rows.base.slice(0, rows.baseLength);
  for (let i = 0; i < move; i++) base.push(rows.tail[i]);
  return new DisplayRows(base, base.length, rows.tail.slice(move));
}

/**
 * The settled part of the transcript as it is on screen, kept between calls. A final appends to the segments: the items
 * and rows from the first one that changed on are rebuilt, and the rest stay the same objects.
 */
type Fold = {
  segments: MeetingSegment[];
  names: MeetingTranscript["voiceNames"];
  /** The other side's timed lines by start: what an echo is checked against. */
  audio: MeetingSegment[];
  /** The rep's timed lines by start, with where each arrived: the ones a new line of the other side can make an echo. */
  rep: { segment: MeetingSegment; arrival: number }[];
  /** The longest of the rep's timed lines, in seconds: how far back from a moment a line can still reach it. */
  repLongest: number;
  tally: Tally;
  learned: Record<number, string>;
  voices: number[];
  /** The rep's lines that are an echo of the call: left out. */
  echo: Set<MeetingSegment>;
  /** The settled lines by `seen`, without the echo. */
  items: DisplayItem[];
  rows: DisplayRows;
  /** The rows after each item. */
  after: Snapshot[];
};

/** The fold of the transcript on screen. Other arrays are computed on their own. */
let fold: Fold | null = null;

function addRep(f: Pick<Fold, "rep" | "repLongest">, segment: MeetingSegment, arrival: number): number {
  if (segment.speaker !== "rep" || segment.start === null) return f.repLongest;
  f.rep.splice(firstPast(f.rep, (line) => line.segment.start as number, segment.start), 0, { segment, arrival });
  return Math.max(f.repLongest, (segment.end ?? segment.start) - segment.start);
}

function buildFold(segments: MeetingSegment[], names: MeetingTranscript["voiceNames"]): Fold {
  const audio = segments
    .filter((segment) => segment.speaker === "prospect" && segment.start !== null)
    .sort((a, b) => (a.start as number) - (b.start as number));
  const reps = { rep: [] as Fold["rep"], repLongest: 0 };
  segments.forEach((segment, arrival) => {
    reps.repLongest = addRep(reps, segment, arrival);
  });
  const tally: Tally = new Map();
  for (const segment of segments) tallyLine(tally, segment);
  const learned = learnedFrom(tally);
  const voices = [...new Set(segments.filter((s) => s.speaker === "prospect" && s.voice != null).map((s) => s.voice as number))];
  const echo = new Set<MeetingSegment>();
  for (const segment of segments) if (isEcho(segment, audio)) echo.add(segment);
  const items: DisplayItem[] = [];
  segments.forEach((segment, arrival) => {
    if (!echo.has(segment)) items.push(itemOf(segment, arrival, names, learned));
  });
  items.sort((a, b) => a.seen - b.seen);
  const after: Snapshot[] = [];
  const rows = settle(new DisplayRows([], 0, displayRows(items, [], voices.length >= 2, after)));
  return { segments, names, audio, rep: reps.rep, repLongest: reps.repLongest, tally, learned, voices, echo, items, rows, after };
}

/** The first item that comes after (seen, arrival) in the order the items are kept: by `seen`, then by arrival. */
function slotAfter(items: DisplayItem[], seen: number, arrival: number): number {
  let low = 0;
  let high = items.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    const item = items[middle];
    if (item.seen > seen || (item.seen === seen && (item.arrival ?? 0) > arrival)) high = middle;
    else low = middle + 1;
  }
  return low;
}

/** The first index whose key is past `value` (the lists are in key order). */
function firstPast<T>(list: T[], key: (item: T) => number, value: number): number {
  let low = 0;
  let high = list.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (key(list[middle]) <= value) low = middle + 1;
    else high = middle;
  }
  return low;
}

/**
 * The rows after the first `k` items, as they were: the fold's rows before the last two, then the two from the snapshot.
 * Returned as the settled rows kept as they are (`baseLength` of the fold's shared array) and a new array with the rest,
 * which always holds the last two: what a rebuild from item `k` appends to.
 */
function prefixAt(f: Fold, k: number): { baseLength: number; rows: MeetingDisplayTurn[] } {
  if (k === 0) return { baseLength: 0, rows: [] };
  const snap = f.after[k - 1];
  const cut = Math.max(0, snap.length - 2);
  const baseLength = Math.min(cut, f.rows.baseLength);
  const rows = f.rows.slice(baseLength, cut);
  if (snap.length >= 2) rows.push(snap.last[0] as MeetingDisplayTurn);
  rows.push(snap.last[1] as MeetingDisplayTurn);
  return { baseLength, rows };
}

/**
 * Brings the fold up to `segments` when they are the fold's own with lines appended (a final) and the same names. Returns
 * false when anything else changed (a line moved or dropped, a voice's name, a voice's channel): then it is built again.
 * What it touches is the new lines and the moment they were said, not the whole call.
 */
function extendFold(f: Fold, segments: MeetingSegment[]): boolean {
  const before = f.segments.length;
  if (segments.length < before) return false;
  for (let i = 0; i < before; i++) if (segments[i] !== f.segments[i]) return false;
  const appended = segments.slice(before);
  for (const segment of appended) tallyLine(f.tally, segment);
  const learned = learnedFrom(f.tally);
  if (JSON.stringify(learned) !== JSON.stringify(f.learned)) return false;
  const voices = [...f.voices];
  for (const segment of appended) {
    if (segment.speaker === "prospect" && segment.voice != null && !voices.includes(segment.voice)) voices.push(segment.voice);
  }
  if (voices.length >= 2 !== f.voices.length >= 2) return false;
  // The other side's new lines go in by their start: an echo check sees them.
  for (const segment of appended) {
    if (segment.speaker === "prospect" && segment.start !== null) f.audio.splice(firstPast(f.audio, (line) => line.start as number, segment.start), 0, segment);
  }
  // Which rep lines can change: an old one whose echo window holds a new line of the other side, and any new one. The old
  // ones are found by their start: a line reaches a moment only if it started at most its length before it.
  const starts = appended.filter((s) => s.speaker === "prospect" && s.start !== null).map((s) => s.start as number);
  const old = new Map<MeetingSegment, number>();
  for (const start of starts) {
    const last = firstPast(f.rep, (line) => line.segment.start as number, start + ECHO_LOOKBACK_S);
    for (let i = last - 1; i >= 0; i--) {
      const { segment, arrival } = f.rep[i];
      const from = segment.start as number;
      if (from < start - ECHO_WINDOW_S - f.repLongest) break;
      if (start >= from - ECHO_LOOKBACK_S && start <= (segment.end ?? from) + ECHO_WINDOW_S) old.set(segment, arrival);
    }
  }
  const checks: { segment: MeetingSegment; arrival: number; fresh: boolean }[] = [...old]
    .sort((a, b) => a[1] - b[1])
    .map(([segment, arrival]) => ({ segment, arrival, fresh: false }));
  appended.forEach((segment, j) => {
    if (segment.speaker === "rep") checks.push({ segment, arrival: before + j, fresh: true });
    f.repLongest = addRep(f, segment, before + j);
  });
  const items = f.items;
  // The earliest place (by seen, then arrival) an item changed at: everything before it is kept.
  let firstSeen = Infinity;
  let firstArrival = Infinity;
  const place = (segment: MeetingSegment, arrival: number, add: boolean) => {
    const seen = segment.seen ?? arrival;
    if (add) {
      items.splice(slotAfter(items, seen, arrival), 0, itemOf(segment, arrival, f.names, learned));
    } else {
      // The item sits just before its slot: it is the last one that is not after (seen, arrival).
      const at = slotAfter(items, seen, arrival) - 1;
      if (at >= 0 && items[at].seen === seen && items[at].arrival === arrival) items.splice(at, 1);
    }
    if (seen < firstSeen || (seen === firstSeen && arrival < firstArrival)) {
      firstSeen = seen;
      firstArrival = arrival;
    }
  };
  // A new line of the other side, or a new line of the rep that is not an echo, is an item from its place on.
  appended.forEach((segment, j) => {
    if (segment.speaker === "rep") return;
    place(segment, before + j, true);
  });
  for (const { segment, arrival, fresh } of checks) {
    const now = isEcho(segment, f.audio);
    // A new rep line has no item yet; an old one has one unless it was an echo.
    const was = fresh ? false : f.echo.has(segment);
    if (now) {
      if (was) continue;
      f.echo.add(segment);
      if (!fresh) place(segment, arrival, false);
    } else {
      if (!was && !fresh) continue;
      f.echo.delete(segment);
      place(segment, arrival, true);
    }
  }
  // The rows from the first changed item on are rebuilt, with the same snapshots as before.
  const k = firstSeen === Infinity ? items.length : slotAfter(items, firstSeen, firstArrival - 1);
  const prefix = prefixAt(f, k);
  f.after.length = k;
  const rows = displayRows(items.slice(k), prefix.rows, voices.length >= 2, f.after, prefix.baseLength);
  f.rows = settle(new DisplayRows(f.rows.base, prefix.baseLength, rows));
  f.learned = learned;
  f.voices = voices;
  f.segments = segments;
  return true;
}

/** The fold for these segments and names: the one on screen, brought up to date, or built again. */
function foldFor(segments: MeetingSegment[], names: MeetingTranscript["voiceNames"]): Fold {
  if (fold && fold.names === names) {
    if (fold.segments === segments) return fold;
    if (extendFold(fold, segments)) return fold;
  }
  fold = buildFold(segments, names);
  return fold;
}

/** Forgets the fold on screen and the rows already made, so the next call builds them from the start (tests compare the two). */
export function forgetFolds(): void {
  fold = null;
  rowsCache = new WeakMap();
  turnsArrayCache = new WeakMap();
}

const voiceIdsCache = new WeakMap<MeetingSegment[], number[]>();
const learnedCache = new WeakMap<MeetingSegment[], Record<number, string>>();

/** The voices heard on the other side, in the order they first spoke. */
function voiceIds(segments: MeetingSegment[]): number[] {
  if (fold?.segments === segments) return fold.voices;
  const cached = voiceIdsCache.get(segments);
  if (cached) return cached;
  const ids = [...new Set(segments.filter((s) => s.speaker === "prospect" && s.voice != null).map((s) => s.voice as number))];
  voiceIdsCache.set(segments, ids);
  return ids;
}

function learnedNames(segments: MeetingSegment[]): Record<number, string> {
  if (fold?.segments === segments) return fold.learned;
  const cached = learnedCache.get(segments);
  if (cached) return cached;
  const tally: Tally = new Map();
  for (const segment of segments) tallyLine(tally, segment);
  const learned = learnedFrom(tally);
  learnedCache.set(segments, learned);
  return learned;
}

/** The rows of each transcript state, once: a state never changes, and the island's clock asks again for the same one. */
let rowsCache = new WeakMap<MeetingTranscript, DisplayRows>();
let turnsArrayCache = new WeakMap<MeetingTranscript, MeetingDisplayTurn[]>();

/** The rows on screen for a transcript state, as settled rows shared with the versions before it and the rows after them. */
export function meetingRows(state: MeetingTranscript): DisplayRows {
  const cached = rowsCache.get(state);
  if (cached) return cached;
  const rows = rowsOf(state);
  rowsCache.set(state, rows);
  return rows;
}

/** The rows as one array (the whole call: a copy, the transcript's length; the live paths read `meetingRows`). */
export function meetingDisplayTurns(state: MeetingTranscript): MeetingDisplayTurn[] {
  const cached = turnsArrayCache.get(state);
  if (cached) return cached;
  const rows = meetingRows(state).slice();
  turnsArrayCache.set(state, rows);
  return rows;
}

function rowsOf(state: MeetingTranscript): DisplayRows {
  const f = foldFor(state.segments, state.voiceNames);
  const nextSeen = state.nextSeen ?? state.segments.length;
  const tails = SPEAKER_ORDER.flatMap((key) => {
    const pending = state.interims[key];
    if (!pending || isEchoTail(state, key, pending)) return [];
    const start = state.interimStarts?.[key] ?? null;
    return [{ seen: state.interimSeen?.[key] ?? nextSeen, speaker: speakerFromKey(key), text: "", pending, start, end: start }];
  }).sort((a, b) => a.seen - b.seen);
  // Nothing still being said: the rows are the fold's own.
  if (!tails.length) return f.rows;
  // The settled rows before the first tail's place are the ones kept; the tails and what settled after them are drawn.
  const k = firstPast(f.items, (item) => item.seen, tails[0].seen);
  const ordered: DisplayItem[] = f.items.slice(k);
  for (const tail of tails) {
    const slot = ordered.findIndex((item) => item.seen > tail.seen);
    ordered.splice(slot === -1 ? ordered.length : slot, 0, tail);
  }
  const prefix = prefixAt(f, k);
  return new DisplayRows(f.rows.base, prefix.baseLength, displayRows(ordered, prefix.rows, f.voices.length >= 2, undefined, prefix.baseLength));
}

export function meetingHasSpeech(state: MeetingTranscript): boolean {
  return state.segments.length > 0 || Object.values(state.interims).some(Boolean);
}

/** Whether the other side of the call said anything (an unanswered call has only the rep). */
export function meetingOtherSideSpoke(state: MeetingTranscript): boolean {
  return state.segments.some((segment) => segment.speaker === "prospect" && segment.text.trim() !== "") || Boolean(state.interims.prospect?.trim());
}

/**
 * What the island says of an ended recording in which nobody spoke. A call that rang (its sound came through) and got
 * no word from either side is an unanswered call, not a fault: it says so and goes, like one on the phone. Anything
 * else (a meeting, or a call none of whose sound arrived) may be a muted or unheard meeting, which the rep should know.
 */
export function silentRecordingNotice(recording: { call: boolean; heard: boolean }): { step: "skipped" | "failed"; message: string } {
  if (recording.call && recording.heard) return { step: "skipped", message: "No answer. Nothing was saved." };
  return { step: "failed", message: "Nothing was transcribed. Check the meeting isn't muted." };
}

/**
 * What is saved: turns in speech order as `SPEAKER: S1` (the rep) and `SPEAKER: S2` (the other side), except that a
 * line from a voice the rep named is saved under that name, so the transcript and the summary know who said it.
 */
export function meetingUploadText(state: MeetingTranscript): string {
  const settled = settleMeeting(state);
  const names = settled.voiceNames ?? {};
  const named = Object.values(names).some((name) => name.trim());
  const turns = named ? namedTurns(settled, names) : meetingTurns(settled).map((turn) => ({ ...turn, who: null }));
  return turns
    .map((turn) => (turn.speaker ? `SPEAKER: ${turn.who ?? SPEAKER_ID[turn.speaker]}\n${turn.text}` : turn.text))
    .join("\n\n")
    .trim();
}

/** The speech-order turns, with the other side split wherever the name the rep gave its voice changes. */
function namedTurns(state: MeetingTranscript, names: Record<number, string>): { speaker: MeetingSpeaker | null; who: string | null; text: string }[] {
  let clock = 0;
  const timed = state.segments.map((segment, arrival) => {
    if (segment.start !== null) clock = segment.start;
    return { segment, at: clock, arrival };
  });
  timed.sort((a, b) => a.at - b.at || a.arrival - b.arrival);
  const meeting = meetingAudio(state.segments);
  const turns: { speaker: MeetingSpeaker | null; who: string | null; text: string }[] = [];
  for (const { segment } of timed) {
    if (isEcho(segment, meeting)) continue;
    const given = segment.speaker === "prospect" && segment.voice != null ? names[segment.voice]?.trim() : "";
    // A line break or ":" in a name would read as a new speaker or as text.
    const who = given ? given.replace(/[\r\n:]+/g, " ").replace(/\s+/g, " ").trim() || null : null;
    const last = turns[turns.length - 1];
    if (last && segment.speaker === null) {
      last.text = joinChunks(last.text, segment.text);
    } else if (last && last.speaker === segment.speaker && (segment.speaker !== "prospect" || last.who === who)) {
      last.text = joinChunks(last.text, segment.text);
    } else if (last && last.speaker === null) {
      last.speaker = segment.speaker;
      last.who = who;
      last.text = joinChunks(last.text, segment.text);
    } else {
      turns.push({ speaker: segment.speaker, who, text: segment.text });
    }
  }
  return turns;
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

/** Who the meeting app showed speaking on the other side, in the order they first spoke. */
export function meetingParticipants(state: MeetingTranscript): string[] {
  const learned = learnedNames(state.segments);
  const names = state.segments
    .filter((segment) => segment.speaker === "prospect")
    .map((segment) => nameOf(segment, state.voiceNames, learned)?.trim())
    .filter((name): name is string => Boolean(name));
  return [...new Set(names)];
}

export type MeetingVoice = { id: number; label: string };

/** The voices heard on the other side, in the order they first spoke, with what each is called now. */
export function meetingVoices(state: MeetingTranscript): MeetingVoice[] {
  const learned = learnedNames(state.segments);
  return voiceIds(state.segments).map((id) => ({ id, label: state.voiceNames?.[id] || learned[id] || `${VOICE_LABEL} ${id}` }));
}

/** The backend says whose voice the line that began at `start` was. */
export function applyVoice(state: MeetingTranscript, start: unknown, voice: unknown): MeetingTranscript {
  const at = seconds(start);
  if (at === null || typeof voice !== "number" || !Number.isInteger(voice) || voice < 1) return state;
  const index = state.segments.findIndex((segment) => segment.speaker === "prospect" && segment.start === at);
  if (index === -1 || state.segments[index].voice === voice) return state;
  const segments = state.segments.slice();
  segments[index] = { ...segments[index], voice };
  return { ...state, segments };
}

/** The rep names a voice (or clears the name with an empty one). */
export function renameVoice(state: MeetingTranscript, voice: number, name: string): MeetingTranscript {
  const clean = name.trim();
  const { [voice]: _old, ...rest } = state.voiceNames ?? {};
  if (!clean && _old === undefined) return state;
  const names = clean ? { ...rest, [voice]: clean } : rest;
  const { voiceNames: _before, ...others } = state;
  return Object.keys(names).length ? { ...others, voiceNames: names } : others;
}

/** Two voices that are one person: every line of `drop` is `keep`'s from now on, and so is its name unless `keep` has one. */
export function mergeVoices(state: MeetingTranscript, keep: number, drop: number): MeetingTranscript {
  if (keep === drop) return state;
  const { [drop]: dropped, ...rest } = state.voiceNames ?? {};
  const names = dropped && !rest[keep] ? { ...rest, [keep]: dropped } : rest;
  const { voiceNames: _before, ...others } = state;
  return {
    ...others,
    segments: state.segments.map((segment) => (segment.speaker === "prospect" && segment.voice === drop ? { ...segment, voice: keep } : segment)),
    ...(Object.keys(names).length ? { voiceNames: names } : {}),
  };
}

/** The lines that began at `starts` are voice `voice`'s (the rep says they were someone else's). */
export function moveLines(state: MeetingTranscript, starts: number[], voice: number): MeetingTranscript {
  const moved = new Set(starts);
  if (!state.segments.some((segment) => segment.speaker === "prospect" && segment.start !== null && moved.has(segment.start) && segment.voice !== voice)) return state;
  return {
    ...state,
    segments: state.segments.map((segment) =>
      segment.speaker === "prospect" && segment.start !== null && moved.has(segment.start) ? { ...segment, voice } : segment,
    ),
  };
}

/** The end of what is on screen, for the desktop island's line. */
export function lastLineOf(rows: RowList<MeetingDisplayTurn>): string {
  const last = rows.at(-1);
  return last ? phraseTail(joinChunks(last.text, last.pending), 110) : "";
}

export function meetingLastLine(state: MeetingTranscript): string {
  return lastLineOf(meetingDisplayTurns(state));
}

export type MeetingOverlayTurn = {
  key: string;
  you: boolean;
  label: string | null;
  text: string;
  pending: string;
  /** The voice that said it, and where its lines began: what the island needs to rename it, merge it or move it. */
  voice: number | null;
  starts: number[];
  /** A colleague of the rep heard with the other side: the island draws it on the rep's side (an older island ignores it). */
  team?: boolean;
};

/**
 * What the notch island shows when opened: the whole conversation, untrimmed. On a call to a
 * known contact (`prospect`), the other side is called by that name instead of "Them".
 */
export function meetingOverlay(
  state: MeetingTranscript,
  { prospect }: { prospect?: string | null } = {},
): { turns: MeetingOverlayTurn[]; voices: MeetingVoice[] } {
  const voices = meetingVoices(state);
  const ctx = { prospect, manyVoices: voices.length >= 2 };
  return { turns: meetingDisplayTurns(state).map((row) => overlayTurnOf(row, ctx)), voices };
}

/** One row as the island draws it. `manyVoices`: with several voices nobody can say which one is the contact. */
export function overlayTurnOf(row: MeetingDisplayTurn, { prospect, manyVoices }: { prospect?: string | null; manyVoices: boolean }): MeetingOverlayTurn {
  const name = prospect?.trim() || null;
  return {
    key: row.key,
    you: row.speaker === "rep",
    label: name && row.speaker === "prospect" && !row.name && !manyVoices ? name : row.label,
    text: row.text,
    pending: row.pending,
    voice: row.voice ?? null,
    starts: row.starts ?? [],
    ...(row.team ? { team: true } : {}),
  };
}
