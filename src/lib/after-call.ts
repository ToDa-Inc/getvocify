import { FOLLOWUP_POLL_FOR_MS, FOLLOWUP_POLL_MS } from "../../shared/ui/home.js";

/** What `GET /calls/{call_sid}` says about a call the rep just hung up. */
export type CallSummary = {
  status?: string | null;
  memoId?: string | null;
  memoStatus?: string | null;
  screeningOutcome?: string | null;
  durationSeconds?: number | null;
};

export type AfterCallLine =
  | { kind: "processing" }
  | { kind: "review"; memoId: string; minutes: number | null }
  | { kind: "saved"; minutes: number | null }
  | { kind: "duration"; minutes: number }
  | null;

const NO_CONVERSATION = new Set(["voicemail", "no_response"]);
const PIPELINE = new Set(["uploading", "transcribing", "extracting", "pending_transcript"]);

function callMinutes(seconds: number | null | undefined): number | null {
  if (seconds == null || !Number.isFinite(Number(seconds))) return null;
  return Math.max(1, Math.round(Number(seconds) / 60));
}

function memoSettled(summary: CallSummary | null | undefined): boolean {
  return Boolean(summary?.memoId && summary.memoStatus && !PIPELINE.has(summary.memoStatus));
}

/** The one line under the contact after the call. «Guardado» only once the memo is approved. */
export function afterCallLine(summary: CallSummary | null | undefined, crm: string | null): AfterCallLine {
  if (!summary || !memoSettled(summary)) return { kind: "processing" };
  const minutes = callMinutes(summary.durationSeconds);
  if (summary.memoStatus === "pending_review") return { kind: "review", memoId: summary.memoId as string, minutes };
  if (summary.memoStatus === "approved" && crm) return { kind: "saved", minutes };
  return minutes ? { kind: "duration", minutes } : null;
}

/** Processing can still reveal there was no conversation, or that the call failed. */
export function afterCallResolution(summary: CallSummary | null | undefined): "no_answer" | "failed" | null {
  if (summary?.screeningOutcome && NO_CONVERSATION.has(summary.screeningOutcome)) return "no_answer";
  if (summary?.status === "failed") return "failed";
  return null;
}

/** Same cadence and bound as the home's follow-up poll; after that the result lands in Falta tu OK. */
export function afterCallPoll(
  summary: CallSummary | null | undefined,
  since: number | null,
  now: number,
): { interval: number | false; since: number | null } {
  if (afterCallResolution(summary) || memoSettled(summary)) return { interval: false, since: null };
  const start = since ?? now;
  return { interval: now - start < FOLLOWUP_POLL_FOR_MS ? FOLLOWUP_POLL_MS : false, since: start };
}
