/**
 * Lista 4 T4 (E10, E11, AFTER_CALL_FLOW_ENABLED): the after-call steps in Hoy's contact panel -
 * CRM proposal, outcome, follow-up, next call. The decisions live here (pure, node-tested);
 * AfterCallReview only renders them. The backend applies the same rules again
 * (backend/app/services/after_call.py) - this module never is the only guard.
 */

export type RepOutcome = "meeting_booked" | "follow_up" | "not_interested" | "disqualified";
export type DealRule = "always" | "meeting_booked" | "follow_up_or_meeting" | "never";

export const REP_OUTCOMES: readonly RepOutcome[] = ["meeting_booked", "follow_up", "not_interested", "disqualified"];
/** Select value for "Otro": the reason is then typed. */
export const OTHER_REASON = "__other__";

/** GET /memos/{id}/after-call. */
export type AfterCallContext = {
  memo_status: string | null;
  provider: string | null;
  suggested_followup_at: string;
  stopper: string | null;
  promised_email: boolean;
  deal_creation_rule: DealRule;
  deal_rule_applies: boolean;
  has_deal: boolean;
  lead_status_options: { on_hold: string | null; lost: string | null } | null;
  proposed_lead_status: Partial<Record<RepOutcome, string | null>> | null;
  lost_reasons: string[];
  rep_outcome: RepOutcome | null;
  followup_at: string | null;
};

/** What the approve/outcome response says the outcome did (`after_call`). */
export type AfterCallHint = {
  rep_outcome?: RepOutcome;
  followup_at?: string | null;
  handoff?: { status: string; id?: string | null; ae_user_id?: string | null } | null;
  signals_resolved?: number;
  crm?: { status: string; warning?: string | null; failed?: string | null; provider?: string } | null;
  deal?: { status: string } | null;
};

export type OutcomeDraft = {
  outcome: RepOutcome | null;
  /** yyyy-mm-dd, the date input's value. */
  followupDate: string;
  /** One of the configured reasons, OTHER_REASON, or "". */
  reason: string;
  otherReason: string;
  /** The lead status the rep picked; null keeps the proposed one. */
  leadStatus: string | null;
};

export type DraftProblem = "outcome" | "reason" | "date";

const DATE_INPUT = /^\d{4}-\d{2}-\d{2}$/;
const CLOSING: ReadonlySet<RepOutcome> = new Set(["not_interested", "disqualified"]);
const RULE_OUTCOMES: Record<DealRule, ReadonlySet<RepOutcome> | null> = {
  always: null,
  meeting_booked: new Set(["meeting_booked"]),
  follow_up_or_meeting: new Set(["meeting_booked", "follow_up"]),
  never: new Set(),
};

/** yyyy-mm-dd of an ISO instant, in the rep's time zone. "" when it isn't a date. */
export function dateInputValue(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function initialDraft(context: AfterCallContext | null | undefined, timeZone?: string): OutcomeDraft {
  return {
    outcome: null,
    followupDate: dateInputValue(context?.suggested_followup_at, timeZone),
    reason: "",
    otherReason: "",
    leadStatus: null,
  };
}

export function needsReason(outcome: RepOutcome | null): boolean {
  return outcome != null && CLOSING.has(outcome);
}

export function effectiveReason(draft: OutcomeDraft): string {
  return (draft.reason === OTHER_REASON ? draft.otherReason : draft.reason).trim();
}

/** Why Confirmar is not available yet: an outcome is required; closing out needs a reason; a
 * follow-up needs a real date (an emptied input is not "use the suggestion" - it is a mistake). */
export function draftProblems(draft: OutcomeDraft): DraftProblem[] {
  if (!draft.outcome) return ["outcome"];
  const problems: DraftProblem[] = [];
  if (needsReason(draft.outcome) && !effectiveReason(draft)) problems.push("reason");
  if (draft.outcome === "follow_up" && !DATE_INPUT.test(draft.followupDate)) problems.push("date");
  return problems;
}

export function canConfirm(draft: OutcomeDraft): boolean {
  return draftProblems(draft).length === 0;
}

/** Mirror of after_call.deal_allowed: may Vocify create a deal for a contact without one? */
export function dealAllowed(rule: DealRule | null | undefined, outcome: RepOutcome | null): boolean {
  const allowed = RULE_OUTCOMES[rule ?? "always"] ?? null;
  if (allowed === null) return true;
  return outcome != null && allowed.has(outcome);
}

/** The one line about the deal under the outcome: nothing when the rule can't matter (a deal
 * exists, the rule is "always", or the CRM ignores it); otherwise whether this outcome creates
 * the deal, or the company's rule in words until an outcome is picked. */
export type DealNote = { kind: "creates" } | { kind: "rule"; rule: Exclude<DealRule, "always"> } | null;

export function dealNote(context: AfterCallContext | null | undefined, outcome: RepOutcome | null): DealNote {
  if (!context || context.has_deal || !context.deal_rule_applies) return null;
  const rule = context.deal_creation_rule;
  if (!rule || rule === "always") return null;
  if (outcome && dealAllowed(rule, outcome)) return { kind: "creates" };
  return { kind: "rule", rule };
}

/** The contact's lead status for the chosen outcome: the proposed value, the values the rep
 * may switch to (only the account's mapped On hold / Lost, never free text), and what goes out. */
export function leadStatusChoice(
  context: AfterCallContext | null | undefined,
  draft: OutcomeDraft,
): { proposed: string | null; options: string[]; value: string | null; editable: boolean } | null {
  if (!context?.proposed_lead_status || !draft.outcome) return null;
  const proposed = context.proposed_lead_status[draft.outcome] ?? null;
  const mapped = [context.lead_status_options?.on_hold, context.lead_status_options?.lost].filter(
    (value): value is string => Boolean(value),
  );
  const options = [...new Set(mapped)];
  const editable = draft.outcome !== "meeting_booked" && options.length > 0;
  const value = editable && draft.leadStatus && options.includes(draft.leadStatus) ? draft.leadStatus : proposed;
  return { proposed, options, value, editable };
}

/** ISO for 09:00 local on the picked day; `offsetMinutes` is the rep's UTC offset (east = +). */
export function followupIso(date: string, offsetMinutes: number): string {
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `${date}T09:00:00${sign}${hh}:${mm}`;
}

export type OutcomePayload = {
  rep_outcome: RepOutcome;
  followup_at?: string;
  disqualify_reason?: string;
  lead_status?: string;
};

/** The outcome fields for POST /approve or /outcome. An untouched suggested date is left out so
 * the backend stores its own suggestion (to the minute); a changed one goes as 09:00 local. */
export function outcomePayload(
  draft: OutcomeDraft,
  context: AfterCallContext | null | undefined,
  { offsetMinutes = 0, timeZone }: { offsetMinutes?: number; timeZone?: string } = {},
): OutcomePayload | null {
  if (!draft.outcome || !canConfirm(draft)) return null;
  const payload: OutcomePayload = { rep_outcome: draft.outcome };
  if (draft.outcome === "follow_up" && draft.followupDate !== dateInputValue(context?.suggested_followup_at, timeZone)) {
    payload.followup_at = followupIso(draft.followupDate, offsetMinutes);
  }
  if (needsReason(draft.outcome)) payload.disqualify_reason = effectiveReason(draft);
  const lead = leadStatusChoice(context, draft);
  if (lead?.editable && lead.value && lead.value !== lead.proposed) payload.lead_status = lead.value;
  return payload;
}

/** An approved memo (auto-approve got there first) takes the outcome on its own endpoint. */
export function confirmTarget(memoStatus: string | null | undefined): "approve" | "outcome" {
  return memoStatus === "approved" ? "outcome" : "approve";
}

/** The follow-up step: the card when an email was promised, else a quiet link until revealed. */
export function followupStep(context: AfterCallContext | null | undefined, revealed: boolean): "card" | "link" {
  return context?.promised_email || revealed ? "card" : "link";
}

/** A CRM write that recorded nothing is an error the rep must see and can retry. */
export function hintFailure(hint: AfterCallHint | null | undefined): string | null {
  return hint?.crm?.status === "failed" ? hint.crm.failed || "failed" : null;
}

/** Catalog keys for the after-call copy, so labels stay in product-catalog.ts. */
export function outcomeLabelKey(outcome: RepOutcome): string {
  return `after_call_outcome_${outcome}`;
}

export function dealRuleKey(rule: Exclude<DealRule, "always">): string {
  return `after_call_deal_rule_${rule}`;
}

export function handoffHintKey(hint: AfterCallHint | null | undefined): string | null {
  const status = hint?.handoff?.status;
  if (!status) return null;
  if (status === "created" || status === "exists") return "after_call_handoff_done";
  if (status === "needs_ae" || status === "invalid_ae") return "after_call_handoff_needs_ae";
  return null;
}
