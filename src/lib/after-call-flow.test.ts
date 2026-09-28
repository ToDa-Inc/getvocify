import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  OTHER_REASON,
  REP_OUTCOMES,
  canConfirm,
  confirmTarget,
  dateInputValue,
  dealAllowed,
  dealNote,
  dealRuleKey,
  draftProblems,
  followupIso,
  followupStep,
  handoffHintKey,
  hintFailure,
  initialDraft,
  leadStatusChoice,
  outcomeLabelKey,
  outcomePayload,
  type AfterCallContext,
  type DealRule,
  type OutcomeDraft,
  type RepOutcome,
} from "./after-call-flow.ts";

const UTC = "UTC";

function context(overrides: Partial<AfterCallContext> = {}): AfterCallContext {
  return {
    memo_status: "pending_review",
    provider: "hubspot",
    suggested_followup_at: "2026-10-05T09:00:00+00:00",
    stopper: "price",
    promised_email: false,
    deal_creation_rule: "always",
    deal_rule_applies: true,
    has_deal: false,
    lead_status_options: { on_hold: "IN_PROGRESS", lost: "UNQUALIFIED" },
    proposed_lead_status: {
      meeting_booked: "OPEN_DEAL",
      follow_up: "IN_PROGRESS",
      not_interested: "UNQUALIFIED",
      disqualified: "UNQUALIFIED",
    },
    lost_reasons: ["No budget", "Not a fit"],
    rep_outcome: null,
    followup_at: null,
    ...overrides,
  };
}

function draft(overrides: Partial<OutcomeDraft> = {}): OutcomeDraft {
  return { ...initialDraft(context(), UTC), ...overrides };
}

describe("after-call draft", () => {
  it("prefills the follow-up date with the suggestion, in the rep's zone", () => {
    assert.equal(initialDraft(context(), UTC).followupDate, "2026-10-05");
    assert.equal(dateInputValue("2026-10-05T23:30:00+00:00", "Europe/Madrid"), "2026-10-06");
    assert.equal(dateInputValue(null), "");
    assert.equal(dateInputValue("nope"), "");
    assert.equal(initialDraft(null).outcome, null);
  });

  it("requires an outcome before Confirmar", () => {
    assert.deepEqual(draftProblems(draft()), ["outcome"]);
    assert.equal(canConfirm(draft()), false);
    assert.equal(canConfirm(draft({ outcome: "meeting_booked" })), true);
  });

  it("requires a reason to close a contact out, typed when it is Otro", () => {
    for (const outcome of ["not_interested", "disqualified"] as RepOutcome[]) {
      assert.deepEqual(draftProblems(draft({ outcome })), ["reason"]);
      assert.equal(canConfirm(draft({ outcome, reason: "No budget" })), true);
      assert.deepEqual(draftProblems(draft({ outcome, reason: OTHER_REASON, otherReason: "  " })), ["reason"]);
      assert.equal(canConfirm(draft({ outcome, reason: OTHER_REASON, otherReason: "Ya tienen proveedor" })), true);
    }
  });

  it("requires a real date for a follow-up", () => {
    assert.equal(canConfirm(draft({ outcome: "follow_up" })), true);
    assert.deepEqual(draftProblems(draft({ outcome: "follow_up", followupDate: "" })), ["date"]);
  });
});

describe("deal rule (E11)", () => {
  const allowed: Record<DealRule, RepOutcome[]> = {
    always: [...REP_OUTCOMES],
    meeting_booked: ["meeting_booked"],
    follow_up_or_meeting: ["meeting_booked", "follow_up"],
    never: [],
  };

  it("matches the backend matrix", () => {
    for (const rule of Object.keys(allowed) as DealRule[]) {
      for (const outcome of REP_OUTCOMES) {
        assert.equal(dealAllowed(rule, outcome), allowed[rule].includes(outcome), `${rule} × ${outcome}`);
      }
    }
    assert.equal(dealAllowed("meeting_booked", null), false);
    assert.equal(dealAllowed(null, null), true);
  });

  it("says nothing when the rule cannot matter", () => {
    assert.equal(dealNote(context(), "follow_up"), null);
    assert.equal(dealNote(context({ deal_creation_rule: "never", has_deal: true }), "follow_up"), null);
    assert.equal(dealNote(context({ deal_creation_rule: "never", deal_rule_applies: false }), "follow_up"), null);
    assert.equal(dealNote(null, "follow_up"), null);
  });

  it("names the rule until the outcome creates the deal", () => {
    const ctx = context({ deal_creation_rule: "meeting_booked" });
    assert.deepEqual(dealNote(ctx, null), { kind: "rule", rule: "meeting_booked" });
    assert.deepEqual(dealNote(ctx, "follow_up"), { kind: "rule", rule: "meeting_booked" });
    assert.deepEqual(dealNote(ctx, "meeting_booked"), { kind: "creates" });
    assert.deepEqual(dealNote(context({ deal_creation_rule: "never" }), "meeting_booked"), { kind: "rule", rule: "never" });
  });
});

describe("lead status", () => {
  it("proposes the account's value and lets the rep switch only between mapped ones", () => {
    const follow = leadStatusChoice(context(), draft({ outcome: "follow_up" }));
    assert.deepEqual(follow, { proposed: "IN_PROGRESS", options: ["IN_PROGRESS", "UNQUALIFIED"], value: "IN_PROGRESS", editable: true });
    const switched = leadStatusChoice(context(), draft({ outcome: "follow_up", leadStatus: "UNQUALIFIED" }));
    assert.equal(switched?.value, "UNQUALIFIED");
    const invented = leadStatusChoice(context(), draft({ outcome: "follow_up", leadStatus: "MADE_UP" }));
    assert.equal(invented?.value, "IN_PROGRESS");
  });

  it("keeps a booked meeting on Open deal and shows nothing without HubSpot or an outcome", () => {
    const booked = leadStatusChoice(context(), draft({ outcome: "meeting_booked", leadStatus: "UNQUALIFIED" }));
    assert.deepEqual(booked, { proposed: "OPEN_DEAL", options: ["IN_PROGRESS", "UNQUALIFIED"], value: "OPEN_DEAL", editable: false });
    assert.equal(leadStatusChoice(context({ proposed_lead_status: null }), draft({ outcome: "follow_up" })), null);
    assert.equal(leadStatusChoice(context(), draft()), null);
    const unmapped = context({ lead_status_options: { on_hold: null, lost: null }, proposed_lead_status: { follow_up: null } });
    assert.deepEqual(leadStatusChoice(unmapped, draft({ outcome: "follow_up" })), { proposed: null, options: [], value: null, editable: false });
  });
});

describe("outcome payload", () => {
  it("is null until the draft can be confirmed", () => {
    assert.equal(outcomePayload(draft(), context()), null);
    assert.equal(outcomePayload(draft({ outcome: "disqualified" }), context()), null);
  });

  it("leaves an untouched suggested date to the backend and sends a changed one as 09:00 local", () => {
    assert.deepEqual(outcomePayload(draft({ outcome: "follow_up" }), context(), { timeZone: UTC }), { rep_outcome: "follow_up" });
    assert.deepEqual(
      outcomePayload(draft({ outcome: "follow_up", followupDate: "2026-10-20" }), context(), { offsetMinutes: 120, timeZone: UTC }),
      { rep_outcome: "follow_up", followup_at: "2026-10-20T09:00:00+02:00" },
    );
    assert.equal(followupIso("2026-10-20", -330), "2026-10-20T09:00:00-05:30");
  });

  it("carries the reason and only a lead status the rep actually changed", () => {
    assert.deepEqual(
      outcomePayload(draft({ outcome: "disqualified", reason: OTHER_REASON, otherReason: " Competidor " }), context()),
      { rep_outcome: "disqualified", disqualify_reason: "Competidor" },
    );
    assert.deepEqual(
      outcomePayload(draft({ outcome: "not_interested", reason: "No budget", leadStatus: "IN_PROGRESS" }), context()),
      { rep_outcome: "not_interested", disqualify_reason: "No budget", lead_status: "IN_PROGRESS" },
    );
    assert.deepEqual(
      outcomePayload(draft({ outcome: "meeting_booked", leadStatus: "UNQUALIFIED" }), context()),
      { rep_outcome: "meeting_booked" },
    );
  });
});

describe("steps", () => {
  it("confirms an approved memo on /outcome, anything else on /approve", () => {
    assert.equal(confirmTarget("approved"), "outcome");
    assert.equal(confirmTarget("pending_review"), "approve");
    assert.equal(confirmTarget(null), "approve");
  });

  it("shows the follow-up card when an email was promised, else a link until revealed", () => {
    assert.equal(followupStep(context({ promised_email: true }), false), "card");
    assert.equal(followupStep(context(), false), "link");
    assert.equal(followupStep(context(), true), "card");
    assert.equal(followupStep(null, false), "link");
  });

  it("turns a CRM write that recorded nothing into a visible failure", () => {
    assert.equal(hintFailure({ crm: { status: "failed", failed: "No contact" } }), "No contact");
    assert.equal(hintFailure({ crm: { status: "written", warning: "x" } }), null);
    assert.equal(hintFailure(null), null);
  });

  it("maps outcomes, rules and handoff hints to catalog keys", () => {
    assert.equal(outcomeLabelKey("follow_up"), "after_call_outcome_follow_up");
    assert.equal(dealRuleKey("never"), "after_call_deal_rule_never");
    assert.equal(handoffHintKey({ handoff: { status: "created" } }), "after_call_handoff_done");
    assert.equal(handoffHintKey({ handoff: { status: "exists" } }), "after_call_handoff_done");
    assert.equal(handoffHintKey({ handoff: { status: "needs_ae" } }), "after_call_handoff_needs_ae");
    assert.equal(handoffHintKey({ handoff: { status: "self_owned" } }), null);
    assert.equal(handoffHintKey({ handoff: null }), null);
  });
});
