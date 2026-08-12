export type ObjectionType =
  | "price"
  | "timing"
  | "authority"
  | "competitor"
  | "status_quo"
  | "trust"
  | "other"
  | "none";

export type Urgency = "low" | "medium" | "high";

export type CallMode = "speakerphone" | "softphone" | "meeting";

export interface ObjectionSuggestion {
  is_objection: boolean;
  objection_type: ObjectionType | string;
  urgency: Urgency | string;
  say_this: string;
  why_it_works: string;
  next_question: string;
  dont_say: string;
}

export interface SuggestRequest {
  transcript_window: string;
  latest_turn: string;
  product_context?: string;
  language?: "auto" | "en" | "es";
  call_mode?: CallMode;
  speaker_role?: "prospect" | "rep" | "unknown";
}

export interface SuggestResultEvent {
  type: "result";
  suggestion: ObjectionSuggestion;
  model: string;
  latency_ms: number;
}

export type SuggestStreamEvent =
  | { type: "token"; text: string }
  | SuggestResultEvent
  | { type: "error"; message: string }
  | { type: "done" };

export const DEFAULT_PRODUCT_CONTEXT = `Product: Vocify — AI voice memos that extract CRM fields and sync to HubSpot after sales calls.
Ideal customer: B2B sales teams / founders who hate typing notes into CRM after calls.
Pain: Lost deal context, delayed CRM hygiene, reps avoid logging calls.
Value: Speak after (or during) the call → structured fields → push to CRM in seconds.
Proof angles: Speeds CRM updates, reduces forgotten follow-ups, keeps pipeline trustworthy.
Tone: Direct, founder-to-founder, no fluff. Spanish or English OK.`;

export const PRODUCT_CONTEXT_STORAGE_KEY = "vocify_copilot_product_context";
