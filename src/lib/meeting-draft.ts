import { meetingHasSpeech, type MeetingTranscript } from "./meeting-transcript.ts";

/** A meeting kept on disk from its first words until the memo exists. */
export type MeetingDraft = {
  id: string;
  userId: string;
  startedAt: number;
  updatedAt: number;
  transcript: MeetingTranscript;
};

function isDraft(value: unknown): value is MeetingDraft {
  const draft = value as MeetingDraft | null;
  return Boolean(
    draft &&
      typeof draft.id === "string" &&
      typeof draft.userId === "string" &&
      typeof draft.startedAt === "number" &&
      Array.isArray(draft.transcript?.turns),
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
    .map((draft) => ({ ...draft, transcript: { turns: draft.transcript.turns, interims: draft.transcript.interims ?? {} } }));
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
