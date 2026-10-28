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
};

export const EMPTY_MEETING_TRANSCRIPT: MeetingTranscript = { segments: [], interims: {} };

const SPEAKER_LABEL: Record<MeetingSpeaker, string> = { rep: "You", prospect: "Them" };
const VOICE_LABEL = "Voice";
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

function meetingAudio(segments: MeetingSegment[]): MeetingAudio {
  return segments
    .filter((segment) => segment.speaker === "prospect" && segment.start !== null)
    .sort((a, b) => (a.start as number) - (b.start as number));
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

function isEcho(segment: MeetingSegment, meeting: MeetingAudio): boolean {
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
  const now = live && liveStart !== undefined ? [{ speaker: "prospect" as const, text: live, start: liveStart, end: start }] : [];
  return isEcho({ speaker: "rep", text: pending, start, end: start }, meetingAudio([...state.segments, ...now]));
}

type DisplayItem = {
  seen: number;
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
function paragraphFor(item: DisplayItem, rows: MeetingDisplayTurn[]): MeetingDisplayTurn | null {
  const last = rows[rows.length - 1];
  if (!last) return null;
  // Another person on the same side (two guests) starts their own paragraph: told apart by the name the meeting app
  // showed, else by voice. A line with neither (a short "sí") goes with whoever was talking.
  const samePerson = (row: MeetingDisplayTurn) =>
    row.name && item.name ? row.name === item.name : row.voice != null && item.voice != null ? row.voice === item.voice : true;
  if (!last.pending && samePerson(last) && (last.speaker === item.speaker || item.speaker === null || last.speaker === null)) {
    return startsNewParagraph(last, item) ? null : last;
  }
  const before = rows[rows.length - 2];
  if (!before || !item.speaker || before.speaker !== item.speaker || before.pending || !samePerson(before)) return null;
  if (last.speaker === item.speaker || last.pending || words(last.text).length > INTERJECTION_WORDS) return null;
  // Said during their paragraph: after it began and before it ended. Not just after it: a one-word answer that
  // comes right behind a question ("¿Qué CRM usáis?" "Salesforce.") is a turn, and the next question is a new bubble.
  const said = last.start;
  if (said == null || before.start == null || before.end == null) return null;
  return said >= before.start - OVERLAP_SLACK_S && said < before.end ? before : null;
}

/** Decided from what is already settled in `row`, so a tail and the final that replaces it always agree. */
function startsNewParagraph(row: MeetingDisplayTurn, item: DisplayItem): boolean {
  if (!row.text || !item.speaker || row.speaker !== item.speaker) return false;
  if (item.start != null && row.end != null && item.start - row.end >= PAUSE_SPLIT_S) return true;
  return /[.!?…]$/.test(row.text) && words(row.text).length >= LONG_PARAGRAPH_WORDS;
}

// Keyed by the segments, and valid only for the names the rep gave the voices when they were built.
type Named<T> = { names: MeetingTranscript["voiceNames"]; value: T };
const settledRowsCache = new WeakMap<MeetingSegment[], Named<MeetingDisplayTurn[]>>();
const settledItemsCache = new WeakMap<MeetingSegment[], Named<DisplayItem[]>>();

/**
 * Builds rows in the order words first showed on screen, never re-sorting what is
 * already there: a bubble keeps its place and key from its first word to its final.
 */
function displayRows(items: DisplayItem[], rows: MeetingDisplayTurn[], manyVoices = false): MeetingDisplayTurn[] {
  const labelOf = (item: DisplayItem) =>
    item.name || (item.voice != null && manyVoices ? `${VOICE_LABEL} ${item.voice}` : item.speaker ? SPEAKER_LABEL[item.speaker] : null);
  for (const item of items) {
    const row = paragraphFor(item, rows);
    if (row) {
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
      continue;
    }
    rows.push({
      key: `u${item.seen}`,
      speaker: item.speaker,
      label: labelOf(item),
      text: item.text,
      pending: item.pending,
      start: item.start,
      end: item.end,
      name: item.name ?? null,
      voice: item.voice ?? null,
      starts: !item.pending && item.speaker === "prospect" && item.start != null ? [item.start] : [],
    });
  }
  return rows;
}

function settledRows(segments: MeetingSegment[], names: MeetingTranscript["voiceNames"]): MeetingDisplayTurn[] {
  const cached = settledRowsCache.get(segments);
  if (cached && cached.names === names) return cached.value;
  const rows = displayRows(settledItems(segments, names), [], voiceIds(segments).length >= 2);
  settledRowsCache.set(segments, { names, value: rows });
  return rows;
}

/** The voices heard on the other side, in the order they first spoke. */
function voiceIds(segments: MeetingSegment[]): number[] {
  return [...new Set(segments.filter((s) => s.speaker === "prospect" && s.voice != null).map((s) => s.voice as number))];
}

/**
 * What the meeting app showed for a voice, when it was the same person nearly every time (two lines at least): the
 * voice then has that name on the lines the app showed nobody for. "Them" beats a wrong name.
 */
function learnedNames(segments: MeetingSegment[]): Record<number, string> {
  const tally = new Map<number, Map<string, number>>();
  for (const segment of segments) {
    if (segment.speaker !== "prospect" || segment.voice == null || !segment.name) continue;
    const names = tally.get(segment.voice) ?? new Map<string, number>();
    names.set(segment.name, (names.get(segment.name) ?? 0) + 1);
    tally.set(segment.voice, names);
  }
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

function settledItems(segments: MeetingSegment[], names: MeetingTranscript["voiceNames"]): DisplayItem[] {
  const cached = settledItemsCache.get(segments);
  if (cached && cached.names === names) return cached.value;
  const meeting = meetingAudio(segments);
  const learned = learnedNames(segments);
  const items = segments
    .map((segment, arrival) => ({ segment, seen: segment.seen ?? arrival }))
    .filter(({ segment }) => !isEcho(segment, meeting))
    .sort((a, b) => a.seen - b.seen)
    .map(({ segment, seen }) => ({
      seen,
      speaker: segment.speaker,
      text: segment.text,
      pending: "",
      start: segment.start,
      end: segment.end,
      name: nameOf(segment, names, learned),
      voice: segment.voice ?? null,
    }));
  settledItemsCache.set(segments, { names, value: items });
  return items;
}

/**
 * Render-ready paragraphs for the live transcript. Unlike the uploaded text (sorted by
 * speech time), they keep the order words first appeared, so a late final never moves
 * or splits a bubble the rep is reading, and a tail keeps its bubble when it settles.
 */
export function meetingDisplayTurns(state: MeetingTranscript): MeetingDisplayTurn[] {
  const nextSeen = state.nextSeen ?? state.segments.length;
  const tails = SPEAKER_ORDER.flatMap((key) => {
    const pending = state.interims[key];
    if (!pending || isEchoTail(state, key, pending)) return [];
    const start = state.interimStarts?.[key] ?? null;
    return [{ seen: state.interimSeen?.[key] ?? nextSeen, speaker: speakerFromKey(key), text: "", pending, start, end: start }];
  }).sort((a, b) => a.seen - b.seen);
  const items = settledItems(state.segments, state.voiceNames);
  const many = voiceIds(state.segments).length >= 2;
  const lastSettled = items.length ? items[items.length - 1].seen : -1;
  if (tails.every((tail) => tail.seen >= lastSettled)) {
    // Usual case: the tails began after everything settled, so they go last.
    return displayRows(tails, settledRows(state.segments, state.voiceNames).map((row) => ({ ...row })), many);
  }
  // Something settled while a tail was still being written: the tail keeps the place it
  // appeared in, above what came after it, exactly where it will settle.
  const ordered = [...items];
  for (const tail of tails) {
    const slot = ordered.findIndex((item) => item.seen > tail.seen);
    ordered.splice(slot === -1 ? ordered.length : slot, 0, tail);
  }
  return displayRows(ordered, [], many);
}

export function meetingHasSpeech(state: MeetingTranscript): boolean {
  return state.segments.length > 0 || Object.values(state.interims).some(Boolean);
}

/** Whether the other side of the call said anything (an unanswered call has only the rep). */
export function meetingOtherSideSpoke(state: MeetingTranscript): boolean {
  return state.segments.some((segment) => segment.speaker === "prospect" && segment.text.trim() !== "") || Boolean(state.interims.prospect?.trim());
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
  /** The voice that said it, and where its lines began: what the island needs to rename it, merge it or move it. */
  voice: number | null;
  starts: number[];
};

/**
 * What the notch island shows when opened: the whole conversation, untrimmed. On a call to a
 * known contact (`prospect`), the other side is called by that name instead of "Them".
 */
export function meetingOverlay(
  state: MeetingTranscript,
  { prospect }: { prospect?: string | null } = {},
): { turns: MeetingOverlayTurn[]; voices: MeetingVoice[] } {
  const name = prospect?.trim() || null;
  const voices = meetingVoices(state);
  return {
    turns: meetingDisplayTurns(state).map((row) => ({
      key: row.key,
      you: row.speaker === "rep",
      // The contact's name is for a conversation with one other voice: with several, nobody can say which is the contact.
      label: name && row.speaker === "prospect" && !row.name && voices.length < 2 ? name : row.label,
      text: row.text,
      pending: row.pending,
      voice: row.voice ?? null,
      starts: row.starts ?? [],
    })),
    voices,
  };
}
