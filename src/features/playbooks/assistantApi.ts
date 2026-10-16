/** The playbook assistant API (/playbook-assistant): guided questions, several documents at once, model calls. */

import { api, ApiError } from "@/shared/lib/api-client";
import type { IntakeResult } from "@/features/playbooks/api";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import type { PlaybookSource } from "@/lib/playbook-doc";

const BASE = "/playbook-assistant";

/** One question the assistant asks. `example` is the customer's own words when real calls raised it. */
export type GapView = {
  key: string;
  kind: "topic" | "real" | "conflict";
  question: string;
  seen: number;
  example: string | null;
  motion_key: string | null;
};

export type GapSession = {
  id: string;
  status: "open" | "done";
  total: number;
  answered: number;
  skipped: number;
  current: GapView | null;
  /** What the Head of Sales said for the current question if saving it failed: nothing dictated is lost. */
  pending_text: string | null;
};

/** The editor content of one call type, as the draft holds it right now. */
export type EditorContent = {
  sales_motion_key: string;
  steps: { step_id: string; label: string; criterion: string; example?: string }[];
  objections: { category: string; guidance: string; id?: string; label?: string; trigger?: string }[];
  qualification: { criterion_id: string; label: string; good?: string }[];
};

export type AnswerResult = { saved_line: string; session: GapSession; editor: EditorContent | null };

/** Several documents at once: the usual intake answer plus the files that could not be read and what disagrees. */
export type IntakeManyResult = IntakeResult & {
  sources: PlaybookSource[];
  failed: { name: string; code: string | null }[];
  conflicts: GapView[];
};

export type ProposalSpeaker = "rep" | "client" | "unknown";

/** Something Vocify learned from a model call, with the passage it comes from. */
export type ModelProposal = {
  id: string;
  kind: "step_example" | "objection_branch";
  step_index?: number;
  category?: string;
  label?: string;
  when?: string;
  text: string;
  excerpt: { speaker: ProposalSpeaker; text: string }[];
  /** Keep a branch that does not fit as an objection of its own, under this name. */
  as_custom?: string;
};

export type ProposeResult = { proposals: ModelProposal[]; speaker_warning: boolean };
export type ApplyResult = { editor: EditorContent; applied: string[]; skipped: { id: string; code: string }[] };
export type RecentCall = { id: string; created_at: string | null; sales_motion_key: string | null; summary: string };
export type ModelCallRequest = {
  motion_key: string;
  transcript?: string;
  memo_id?: string;
  scope?: { kind: "whole" } | { kind: "moment"; text: string };
  note?: string;
};

export type TrialSource = "real" | "document" | "typical";
/** One thing a customer might say; `verdict` is what the Head of Sales decided about it (null until then). */
export type TrialCase = { id: string; source: TrialSource; client_text: string; verdict: string | null };
export type RunCard = { say_this: string; source_id: string | null; objection_type: string | null };
/** What live help would show for a case: what the turn check named and the card (null when it would show nothing). */
export type TrialRun = { detected: string; entry_id: string | null; label: string | null; card: RunCard | null; grounded: boolean };
export type TrialResultData = {
  approved: number;
  total: number;
  /** Null below three decided cases: a percentage of two says nothing. */
  percent: number | null;
  weak_topics: string[];
  warn: boolean;
  can_activate: boolean;
};
export type Trial = {
  id: string;
  motion_key: string;
  status: "open" | "done";
  total: number;
  decided: number;
  cases: TrialCase[];
  current_id: string | null;
  runs: Record<string, TrialRun>;
  result: TrialResultData;
};
export type Verdict = "approve" | "corrected" | "unknown" | "never_say" | "branch" | "own";
export type VerdictOutcome = { run: TrialRun | null; similar: { text: string; run: TrialRun } | null; result: TrialResultData; trial: Trial };
export type ActivateOutcome = { published: string[]; failed: { key: string; code: string }[] };

/** The API says the assistant's tables are not in the database yet: a calm "come back soon", not a failure. */
export function isNotActivated(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 503) return false;
  const detail = (error.data as { detail?: { code?: string } } | null | undefined)?.detail;
  return detail?.code === "not_activated";
}

const SLOW = { timeoutMs: 120_000 };

export const assistantApi = {
  // Several documents become one draft per call type; the model reads each, so it waits well past the default 20 s.
  intake: (sources: SourceInput[]) => api.post<IntakeManyResult>(`${BASE}/intake`, { sources }, { timeoutMs: 240_000 }),

  startGaps: (body: { motion_key?: string; lang: "es" | "en" }) => api.post<GapSession>(`${BASE}/gaps/session`, body),
  currentGaps: () => api.get<{ session: GapSession | null }>(`${BASE}/gaps/session/current`),
  answerGap: (sessionId: string, gapKey: string, source: SourceInput) =>
    api.post<AnswerResult>(`${BASE}/gaps/session/${encodeURIComponent(sessionId)}/answer`, { gap_key: gapKey, ...source }, SLOW),
  skipGap: (sessionId: string, gapKey: string) =>
    api.post<GapSession>(`${BASE}/gaps/session/${encodeURIComponent(sessionId)}/skip`, { gap_key: gapKey }),
  undoGap: (sessionId: string, gapKey: string) =>
    api.post<GapSession>(`${BASE}/gaps/session/${encodeURIComponent(sessionId)}/undo`, { gap_key: gapKey }),

  startTrial: (body: { motion_key?: string; lang: "es" | "en"; fresh?: boolean }) => api.post<Trial>(`${BASE}/trial`, body, SLOW),
  runCase: (trialId: string, caseId: string) =>
    api.post<{ case: { id: string; source: TrialSource; client_text: string }; run: TrialRun }>(
      `${BASE}/trial/${encodeURIComponent(trialId)}/cases/${encodeURIComponent(caseId)}/run`,
      undefined,
      SLOW,
    ),
  decide: (trialId: string, caseId: string, body: { verdict: Verdict; text?: string; when?: string }) =>
    api.post<VerdictOutcome>(`${BASE}/trial/${encodeURIComponent(trialId)}/cases/${encodeURIComponent(caseId)}/verdict`, body, SLOW),
  activateTrial: (trialId: string) => api.post<ActivateOutcome>(`${BASE}/trial/${encodeURIComponent(trialId)}/activate`),

  recentCalls: () => api.get<{ calls: RecentCall[] }>(`${BASE}/model-calls/recent`),
  proposeFromCall: (body: ModelCallRequest) => api.post<ProposeResult>(`${BASE}/model-calls/propose`, body, SLOW),
  applyProposals: (motionKey: string, proposals: ModelProposal[]) =>
    api.post<ApplyResult>(`${BASE}/model-calls/apply`, { motion_key: motionKey, proposals }),
};
