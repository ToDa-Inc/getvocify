import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  callTypeFrom,
  changesFrom,
  connectedCrmName,
  crmForType,
  crmFor,
  defaultKept,
  emailFrom,
  meetingFrom,
  pendingItems,
  pollDelayMs,
  retypedTo,
  type PostCall,
} from "./post-call.ts";

describe("changesFrom", () => {
  it("lists real changes with the review screen's field keys", () => {
    const changes = changesFrom([
      { field_name: "hs_lead_status", field_label: "Lead status", object_type: "contacts", current_value: "NEW", new_value: "IN_PROGRESS", extraction_confidence: 0.9 },
      { field_name: "phone", field_label: "Phone", object_type: "contacts", current_value: "+34 600", new_value: "+34 600" },
      { field_name: "amount", field_label: "Amount", new_value: 196, extraction_confidence: 0.55 },
      { field_name: "notes", field_label: "Notes", new_value: "" },
    ]);
    assert.deepEqual(changes, [
      { key: "contacts:hs_lead_status", label: "Lead status", from: "NEW", to: "IN_PROGRESS", check: false },
      { key: "deals:amount", label: "Amount", from: null, to: "196", check: true },
    ]);
  });

  it("only flags what the extraction scored under 'needs review'; unknown confidence is not a flag", () => {
    const [unknown, sure] = changesFrom([
      { field_name: "a", field_label: "A", new_value: "x" },
      { field_name: "b", field_label: "B", new_value: "y", extraction_confidence: 0.7 },
    ]);
    assert.equal(unknown.check, false);
    assert.equal(sure.check, false);
  });

  it("ticks only what isn't flagged", () => {
    const changes = changesFrom([
      { field_name: "a", field_label: "A", new_value: "x", extraction_confidence: 0.95 },
      { field_name: "b", field_label: "B", new_value: "y", extraction_confidence: 0.4 },
    ]);
    assert.deepEqual(defaultKept(changes), ["deals:a"]);
  });
});

describe("crmFor", () => {
  const ready = { status: "pending_review", hubspotContactId: "879829962968" };
  it("writes while extraction runs, then offers one click only with a contact", () => {
    assert.equal(crmFor({ status: "extracting" }).stage, "writing");
    assert.equal(crmFor(ready, [{ field_name: "a", field_label: "A", new_value: "x" }]).canApprove, true);
    assert.equal(crmFor({ ...ready, hubspotContactId: null }, [{ field_name: "a", field_label: "A", new_value: "x" }]).canApprove, false);
  });

  it("is done when auto-approve already wrote it, and sends failures and empty proposals to review", () => {
    assert.equal(crmFor({ status: "approved" }).stage, "done");
    assert.equal(crmFor({ status: "failed" }).stage, "review");
    assert.equal(crmFor(ready, []).stage, "review");
  });
});

describe("emailFrom", () => {
  it("only shows a draft that exists", () => {
    assert.deepEqual(emailFrom({ status: "ready", recipientName: "Marta" }), { state: "ready", to: "Marta" });
    assert.equal(emailFrom({ status: "generating" }), null);
    assert.equal(emailFrom({ status: "unavailable" }), null);
    assert.equal(emailFrom(null), null);
  });
});

describe("meetingFrom", () => {
  const agreed = { proposal_id: "p1", agreement: "agreed", starts_at: "2026-10-07T08:00:00Z", timezone: "Europe/Madrid", decision: "pending", needs_review: false };

  it("offers only a meeting the call agreed, in its own time zone", () => {
    const meeting = meetingFrom(agreed, "en-GB");
    assert.equal(meeting?.state, "pending");
    assert.match(meeting?.when ?? "", /Wed.*7 Oct.*10:00/);
  });

  it("asks for a look when the time isn't clear, and stays quiet when nothing was agreed", () => {
    assert.equal(meetingFrom({ ...agreed, needs_review: true })?.state, "check");
    assert.equal(meetingFrom({ ...agreed, agreement: "unknown" }), null);
    assert.equal(meetingFrom({ ...agreed, decision: "omitted" }), null);
    assert.equal(meetingFrom({ ...agreed, decision: "accepted" })?.state, "added");
    assert.equal(meetingFrom(null), null);
  });
});

describe("pendingItems", () => {
  const base: PostCall = { memoId: "m", contactName: null, stage: "done", changes: [], canApprove: false, email: null, meeting: null, notes: true };
  it("counts what still needs the rep", () => {
    assert.equal(pendingItems(base), 0);
    assert.equal(
      pendingItems({ ...base, stage: "ready", email: { state: "ready", to: null }, meeting: { proposalId: "p", state: "pending", when: null } }),
      3,
    );
    assert.equal(pendingItems({ ...base, email: { state: "skipped", to: null }, meeting: { proposalId: "p", state: "added", when: null } }), 0);
  });
});

describe("pollDelayMs", () => {
  it("checks quickly at first, then gently", () => {
    assert.equal(pollDelayMs(0), 1500);
    assert.equal(pollDelayMs(30), 4000);
  });
});

describe("callTypeFrom", () => {
  const name = (key: string, label?: string | null) => label || { discovery: "Cold call", closing: "Demo and close" }[key] || key;
  const view = {
    sales_motion_key: "discovery",
    can_change: true,
    options: [
      { key: "discovery", label: null },
      { key: "closing", label: "Demo de producto" },
      { key: "internal", label: null },
    ],
  };

  it("names the call's type and offers the others when it can be changed", () => {
    assert.deepEqual(callTypeFrom(view, name), {
      key: "discovery",
      label: "Cold call",
      options: [
        { key: "closing", label: "Demo de producto" },
        { key: "internal", label: "internal" },
      ],
    });
  });

  it("shows it without options to someone who can't change it, and nothing without a type", () => {
    assert.deepEqual(callTypeFrom({ ...view, can_change: false }, name)?.options, []);
    assert.equal(callTypeFrom({ ...view, sales_motion_key: null }, name), null);
    assert.equal(callTypeFrom(null, name), null);
  });

  it("puts the old type back among the options, in the page's order", () => {
    const type = callTypeFrom(view, name)!;
    const next = retypedTo(type, "closing", ["discovery", "closing", "internal"]);
    assert.deepEqual(next, {
      key: "closing",
      label: "Demo de producto",
      options: [
        { key: "discovery", label: "Cold call" },
        { key: "internal", label: "internal" },
      ],
    });
    assert.equal(retypedTo(type, "nope", []), null);
  });
});

describe("crmForType", () => {
  const crm = { stage: "ready" as const, changes: [{ key: "contacts:a", label: "A", from: null, to: "x", check: false }], canApprove: true };
  it("an internal conversation has nothing for the CRM; any other type keeps the memo's changes", () => {
    assert.deepEqual(crmForType("internal", crm), { stage: "internal", changes: [], canApprove: false, note: undefined });
    assert.equal(crmForType("discovery", crm), crm);
    assert.equal(crmForType(null, crm), crm);
    assert.equal(pendingItems({ memoId: "m", contactName: null, ...crmForType("internal", crm), email: null, meeting: null, notes: false }), 0);
  });
});

describe("connectedCrmName", () => {
  const names = { hubspot: { name: "HubSpot" }, pipedrive: { name: "Pipedrive" } };
  it("names the connected CRM, not one that was disconnected", () => {
    const connections = [
      { provider: "hubspot", status: "disconnected" },
      { provider: "pipedrive", status: "connected" },
    ];
    assert.equal(connectedCrmName(connections, names), "Pipedrive");
  });
  it("never guesses: nothing connected, an unknown provider or no list is null", () => {
    assert.equal(connectedCrmName([{ provider: "hubspot", status: "disconnected" }], names), null);
    assert.equal(connectedCrmName([{ provider: "zoho", status: "connected" }], names), null);
    assert.equal(connectedCrmName(undefined, names), null);
  });
});
