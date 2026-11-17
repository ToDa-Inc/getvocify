import { meetingHasSpeech, normalizeMeetingTranscript, type MeetingSegment, type MeetingTranscript } from "./meeting-transcript.ts";

/** A meeting kept on disk from its first words until the memo exists. */
export type MeetingDraft = {
  id: string;
  userId: string;
  startedAt: number;
  updatedAt: number;
  transcript: MeetingTranscript;
  /** What the rep typed during the meeting. */
  notes?: string;
  /** The CRM contact on screen when the call started; the memo is born with it. */
  contact?: { hubspotId: string; name: string | null };
  /** The deal or company open on screen when the call started; the call is saved there too. */
  record?: { dealId?: string; companyId?: string };
  /** Where the call happened, as the Mac saw it: the app or page, and whether that makes it a call or a meeting. */
  source?: CallSourceInfo;
  /** The channel the rep switched to on the island (types by channel); absent, `source` decides. */
  channel?: "call" | "meeting";
  /** The call type the island showed when the call ended; absent, Vocify reads it after. */
  type?: string;
  /** Who chose `type`: the rep's pick is final, Vocify's suggestion can still be corrected after the
   * call. Drafts saved before this field existed are sent as Vocify's. */
  typeSource?: "rep" | "vocify";
};

export type CallSourceInfo = { name: string; kind: "call" | "meeting" | null };

/** A draft without its segments: what an append carries next to the segments it adds. */
export type DraftHead = Omit<MeetingDraft, "transcript"> & { transcript: Omit<MeetingTranscript, "segments"> };

/**
 * What a save sends. The whole draft, or (when the desktop app keeps appends) only the segments added since the last
 * save, from index `from` on, with the rest of the draft.
 */
export type DraftSave =
  | { kind: "full"; draft: MeetingDraft }
  | { kind: "append"; id: string; from: number; segments: MeetingSegment[]; draft: DraftHead };

/** The segments of the draft as the desktop app last saved them (the same objects), or null when none are saved. */
export type SavedSegments = { id: string; segments: MeetingSegment[] } | null;

/**
 * The save for a draft. An append when the segments saved before are still the first ones (the same objects, in the same
 * places): an edit of a line (a voice) makes a new object, and then the whole draft goes. A save then costs what is new,
 * not the length of the call.
 */
export function draftSaveFor(draft: MeetingDraft, saved: SavedSegments, canAppend: boolean): DraftSave {
  const { segments, ...transcript } = draft.transcript;
  if (!canAppend || !saved || saved.id !== draft.id || segments.length < saved.segments.length) return { kind: "full", draft };
  if (segments !== saved.segments) {
    for (let index = 0; index < saved.segments.length; index++) {
      if (segments[index] !== saved.segments[index]) return { kind: "full", draft };
    }
  }
  return {
    kind: "append",
    id: draft.id,
    from: saved.segments.length,
    segments: segments.slice(saved.segments.length),
    draft: { ...draft, transcript },
  };
}

function isDraft(value: unknown): value is MeetingDraft {
  const draft = value as MeetingDraft | null;
  return Boolean(
    draft &&
      typeof draft.id === "string" &&
      typeof draft.userId === "string" &&
      typeof draft.startedAt === "number" &&
      Boolean(draft.transcript) &&
      (Array.isArray(draft.transcript.segments) || Array.isArray((draft.transcript as { turns?: unknown }).turns)),
  );
}

/**
 * Splits stored drafts into the signed-in user's meetings worth sending (oldest
 * first) and empty ones safe to delete. Other users' drafts are left untouched.
 */
export function sortDrafts(
  stored: unknown[],
  userId: string,
): { send: MeetingDraft[]; discard: MeetingDraft[] } {
  const mine = stored
    .filter(isDraft)
    .filter((draft) => draft.userId === userId)
    .map((draft) => ({ ...draft, transcript: normalizeMeetingTranscript(draft.transcript) }));
  return {
    send: mine.filter((draft) => meetingHasSpeech(draft.transcript)).sort((a, b) => a.startedAt - b.startedAt),
    discard: mine.filter((draft) => !meetingHasSpeech(draft.transcript)),
  };
}

export function meetingStartedLabel(draft: MeetingDraft): string {
  return new Date(draft.startedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function draftMinutes(draft: MeetingDraft): number {
  return Math.max(1, Math.round((draft.updatedAt - draft.startedAt) / 60000));
}
