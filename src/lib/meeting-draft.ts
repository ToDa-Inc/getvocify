import { meetingHasSpeech, normalizeMeetingTranscript, type MeetingTranscript } from "./meeting-transcript.ts";

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
  /** Where the call happened, as the Mac saw it: the app or page, and whether that makes it a call or a meeting. */
  source?: CallSourceInfo;
};

export type CallSourceInfo = { name: string; kind: "call" | "meeting" | null };

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
