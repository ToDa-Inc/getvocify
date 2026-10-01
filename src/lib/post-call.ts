/**
 * The Mac notch island's card after a recorded call. Every row comes from something the
 * backend produced for this call and that still needs the rep; nothing is invented, and
 * a row that doesn't apply is simply absent.
 *
 * No `@/` imports: this file runs under node --test.
 */
import { proposedFieldKey, type ProposedUpdate } from "./extraction-omit.ts";
import { CONFIDENCE } from "../shared/lib/constants.ts";

/** One proposed CRM change, as the island lists it. */
export type PostCallChange = {
  /** `object_type:field_name`, the key the review screen omits fields by. */
  key: string;
  label: string;
  from: string | null;
  to: string;
  /** Extraction confidence under CONFIDENCE.MEDIUM ("needs review"): shown, unticked. */
  check: boolean;
};

export type PostCallCrmStage =
  /** The memo is being extracted. */
  | "writing"
  /** Changes ready: approve here (when safe) or review in Vocify. */
  | "ready"
  /** Approved: the write waits out the undo window, then runs. */
  | "applying"
  | "done"
  /** Needs the review screen (a choice to make, or something went wrong). */
  | "review";

export type PostCallEmail = {
  /** ready: drafted, not sent. skipped/sent: settled, shown briefly then gone. */
  state: "ready" | "skipped" | "sent";
  /** Who it's for, as extracted. */
  to: string | null;
};

export type PostCallMeeting = {
  proposalId: string;
  /** "agreed" with a time: one click adds it to the CRM. "check": needs a correction in review. */
  state: "pending" | "check" | "added";
  /** e.g. "Tue 7 Oct, 10:00", in the proposal's time zone. */
  when: string | null;
};

export type PostCall = {
  memoId: string;
  contactName: string | null;
  stage: PostCallCrmStage;
  changes: PostCallChange[];
  /** One click is safe: the memo knows its contact and nothing needs a choice. */
  canApprove: boolean;
  /** How many changes were written, once done. */
  applied?: number;
  /** While applying: epoch ms until which Undo still stops the write. */
  undoUntil?: number;
  note?: string;
  email: PostCallEmail | null;
  meeting: PostCallMeeting | null;
  /** The memo has a call note to read. */
  notes: boolean;
  /** Asked once, after several skipped emails in a row. */
  offerStopEmails?: boolean;
};

type Update = ProposedUpdate & { extraction_confidence?: number | null };

function text(value: unknown): string {
  return value == null ? "" : String(value).replace(/\s+/g, " ").trim();
}

/** The changes worth naming: a new value that differs from what the CRM has. */
export function changesFrom(proposed: Update[] | null | undefined): PostCallChange[] {
  const changes: PostCallChange[] = [];
  for (const update of proposed ?? []) {
    const key = proposedFieldKey(update);
    const to = text(update.new_value);
    const from = text(update.current_value);
    if (!key || !to || to === from) continue;
    const confidence = typeof update.extraction_confidence === "number" ? update.extraction_confidence : null;
    changes.push({
      key,
      label: text(update.field_label) || text(update.field_name),
      from: from || null,
      to,
      check: confidence !== null && confidence < CONFIDENCE.MEDIUM,
    });
  }
  return changes;
}

/** The changes ticked by default: everything the extraction is sure enough about. */
export function defaultKept(changes: PostCallChange[]): string[] {
  return changes.filter((change) => !change.check).map((change) => change.key);
}

type FollowupView = { status?: string | null; recipientName?: string | null };

export function emailFrom(view: FollowupView | null | undefined): PostCallEmail | null {
  const status = view?.status;
  if (status !== "ready" && status !== "skipped" && status !== "sent") return null;
  return { state: status, to: text(view?.recipientName) || null };
}

type MeetingProposal = {
  proposal_id?: unknown;
  agreement?: unknown;
  starts_at?: unknown;
  timezone?: unknown;
  decision?: unknown;
  needs_review?: unknown;
};

export function meetingWhen(startsAt: string, timeZone: string | null, locale = "en-GB"): string | null {
  const date = new Date(startsAt);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(locale, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timeZone || undefined,
    }).format(date);
  } catch {
    return null;
  }
}

/** Only a meeting the call actually agreed. Accepting creates a CRM meeting task, not an invite. */
export function meetingFrom(proposal: MeetingProposal | null | undefined, locale?: string): PostCallMeeting | null {
  const proposalId = text(proposal?.proposal_id);
  if (!proposal || !proposalId || proposal.agreement !== "agreed") return null;
  const decision = text(proposal.decision) || "pending";
  const startsAt = text(proposal.starts_at);
  const when = startsAt ? meetingWhen(startsAt, text(proposal.timezone) || null, locale) : null;
  if (decision === "accepted" || decision === "corrected") return { proposalId, state: "added", when };
  if (decision !== "pending") return null;
  return { proposalId, state: proposal.needs_review || !when ? "check" : "pending", when };
}

/** The CRM part for a memo's status; `proposed` is the review preview, fetched once ready. */
export function crmFor(
  memo: { status: string; hubspotContactId?: string | null },
  proposed?: Update[] | null,
): Pick<PostCall, "stage" | "changes" | "canApprove" | "note"> {
  switch (memo.status) {
    case "approved":
      return { stage: "done", changes: [], canApprove: false };
    case "pending_review": {
      const changes = changesFrom(proposed);
      if (!changes.length) return { stage: "review", changes, canApprove: false, note: "Nothing to change in the CRM" };
      return { stage: "ready", changes, canApprove: Boolean(memo.hubspotContactId) };
    }
    case "failed":
    case "rejected":
      return { stage: "review", changes: [], canApprove: false, note: "Needs a look" };
    default:
      return { stage: "writing", changes: [], canApprove: false };
  }
}

/** What still needs the rep: the count on the closed island, and whether the card can go. */
export function pendingItems(postCall: PostCall | null): number {
  if (!postCall) return 0;
  let count = 0;
  if (postCall.stage === "ready" || postCall.stage === "review") count += 1;
  if (postCall.email?.state === "ready") count += 1;
  if (postCall.meeting && postCall.meeting.state !== "added") count += 1;
  return count;
}

/** Skipped emails in a row before Vocify asks, once, whether to stop drafting them. */
export const SKIPS_BEFORE_ASKING = 3;

/** How long Approve can still be undone before the write runs. */
export const UNDO_MS = 5000;

/** Waits between status checks: quick at first, gentler while extraction runs long. */
export function pollDelayMs(attempt: number): number {
  return attempt < 10 ? 1500 : 4000;
}

/** Long enough for a slow extraction or email draft; after that the memo is left to Vocify. */
export const POST_CALL_GIVE_UP_MS = 4 * 60 * 1000;
