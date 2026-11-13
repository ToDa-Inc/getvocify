import { api } from "@/shared/lib/api-client";

const BASE = "/playbook-assistant/suggestions";
const SLOW = { timeoutMs: 60_000 };

export type SuggestionKind = "objection" | "question" | "worked" | "opportunity";
export type SuggestionAfter = "advanced" | "stalled" | "ended" | "unknown";
export type DismissReason = "isolated" | "not_applicable" | "covered";

/** One turn of the exchange the suggestion comes from: the words as said, and what was meant (absent on older reads). */
export type SuggestionTurn = { who: "client" | "rep"; quote: string; said: string | null };

/** What the team's calls taught, grouped by topic and call type (GET /playbook-assistant/suggestions). */
export type Suggestion = {
  key: string;
  kind: SuggestionKind;
  motion: string;
  motion_label: string;
  title: string;
  count: number;
  reps: string[];
  memo_ids: string[];
  last_at: string | null;
  /** Objections: calls that ended or stalled right after it. */
  lost: number;
  /** Questions: times nobody answered it. */
  unanswered: number;
  examples: { memo_id: string; observed_at: string; rep: string; turns: SuggestionTurn[]; after: SuggestionAfter | null }[];
  /** The ready draft: a colleague's words after which the call went on, else a line written from the playbook and the material. */
  draft: string | null;
  draft_from: "colleague" | "vocify" | null;
  why: string | null;
  use_when: string | null;
};

export type SuggestionAnswer = { id: string; label: string | null; category: string };

export type SuggestionsBody = {
  suggestions: Suggestion[];
  /** The published answers of each call type, to say which one already covers a suggestion. */
  answers: Record<string, SuggestionAnswer[]>;
  /** How many the head of sales has taken into the playbook so far. */
  learned: number;
};

export const suggestionsApi = {
  list: () => api.get<SuggestionsBody>(BASE),
  accept: (key: string, text: string) =>
    api.post<SuggestionsBody & { status: string; motion: string; published: boolean }>(`${BASE}/${encodeURIComponent(key)}/accept`, { text }, SLOW),
  dismiss: (key: string, reason: DismissReason, coveredBy?: string) =>
    api.post<SuggestionsBody & { status: string }>(`${BASE}/${encodeURIComponent(key)}/dismiss`, { reason, covered_by: coveredBy ?? null }),
  /** «Completar con Vocify»: an answer written from the company's material only; text null when it does not hold it. */
  draft: (key: string) => api.post<{ text: string | null }>(`${BASE}/${encodeURIComponent(key)}/draft`, undefined, SLOW),
  undo: (key: string) => api.post<SuggestionsBody & { status: string }>(`${BASE}/${encodeURIComponent(key)}/undo`),
};

export const SUGGESTIONS_QUERY = ["playbook-assistant", "suggestions"] as const;
