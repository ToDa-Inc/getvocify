/**
 * What the Mac notch island shows after a recorded call: the memo being written,
 * then the CRM update it proposes for the call's contact, one click from done.
 *
 * No `@/` imports: this file runs under node --test.
 */

export type PostCallStage =
  /** The memo is being extracted. */
  | "writing"
  /** The update is ready; approve here or review it in Vocify. */
  | "ready"
  | "approving"
  /** Written to the CRM. */
  | "done"
  /** Needs the review screen (a choice to make, or something went wrong). */
  | "review";

export type PostCallUpdate = { label: string; value: string };

export type PostCall = {
  stage: PostCallStage;
  memoId: string;
  contactName: string | null;
  /** The first few proposed changes, as the island shows them. */
  updates: PostCallUpdate[];
  /** How many changes in total. */
  total: number;
  /** One click is safe: the memo knows its contact and nothing needs a choice. */
  canApprove: boolean;
  /** A short reason when the stage is "review". */
  note?: string;
};

type ProposedUpdate = {
  field_label?: string | null;
  field_name?: string | null;
  current_value?: string | null;
  new_value?: string | null;
};

const SHOWN = 3;
const VALUE_CHARS = 42;

function clip(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`;
}

/** The changes worth naming: a new value that differs from what the CRM has. */
export function summarizeUpdates(proposed: ProposedUpdate[] | null | undefined): { updates: PostCallUpdate[]; total: number } {
  const real = (proposed ?? []).filter((update) => {
    const next = (update.new_value ?? "").trim();
    return next && next !== (update.current_value ?? "").trim();
  });
  return {
    updates: real.slice(0, SHOWN).map((update) => ({
      label: clip(update.field_label || update.field_name || "Field", 28),
      value: clip(update.new_value ?? "", VALUE_CHARS),
    })),
    total: real.length,
  };
}

/**
 * The island's state for a memo's status. `proposed` is the review preview's
 * changes, only fetched once the memo is ready.
 */
export function postCallFor(
  memo: { id: string; status: string; hubspotContactId?: string | null },
  contactName: string | null,
  proposed?: ProposedUpdate[] | null,
): PostCall {
  const base = { memoId: memo.id, contactName, updates: [], total: 0, canApprove: false };
  switch (memo.status) {
    case "approved":
      return { ...base, stage: "done" };
    case "pending_review": {
      const { updates, total } = summarizeUpdates(proposed);
      if (!total) return { ...base, stage: "review", note: "Nothing to change" };
      return { ...base, stage: "ready", updates, total, canApprove: Boolean(memo.hubspotContactId) };
    }
    case "failed":
    case "rejected":
      return { ...base, stage: "review", note: "Needs a look" };
    default:
      return { ...base, stage: "writing" };
  }
}

/** Waits between status checks: quick at first, gentler while extraction runs long. */
export function pollDelayMs(attempt: number): number {
  return attempt < 10 ? 1500 : 4000;
}

/** Long enough for a slow extraction; after that the memo is left to the dashboard. */
export const POST_CALL_GIVE_UP_MS = 4 * 60 * 1000;
