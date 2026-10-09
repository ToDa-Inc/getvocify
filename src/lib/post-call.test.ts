import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  callTypeFrom,
  changesFrom,
  crmForType,
  crmFor,
  defaultKept,
  emailFrom,
  meetingFrom,
  noteMarkdown,
  pendingItems,
  pollDelayMs,
  retypedTo,
  summaryLines,
  withEdits,
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
      { key: "contacts:hs_lead_status", label: "Lead status", object: "contact", from: "NEW", to: "IN_PROGRESS", value: "IN_PROGRESS", options: [], multiple: false, editable: true, check: false },
      { key: "deals:amount", label: "Amount", object: "deal", from: null, to: "196", value: "196", options: [], multiple: false, editable: true, check: true },
    ]);
  });

  it("shows option labels, keeps the values to write, and knows a checkbox list", () => {
    const [stage, tools] = changesFrom([
      {
        field_name: "lifecyclestage", field_label: "Lifecycle stage", object_type: "contacts",
        current_value: "lead", new_value: "opportunity",
        options: [{ value: "lead", label: "Lead" }, { value: "opportunity", label: "Opportunity" }],
      },
      {
        field_name: "tools", field_label: "Tools", object_type: "companies", new_value: "excel;holded", multiple: true,
        options: [{ value: "excel", label: "Excel" }, { value: "holded", label: "Holded" }, { value: "", label: "—" }],
      },
    ]);
    assert.equal(stage.from, "Lead");
    assert.equal(stage.to, "Opportunity");
    assert.equal(stage.value, "opportunity");
    assert.equal(stage.multiple, false);
    assert.equal(tools.object, "company");
    assert.equal(tools.to, "Excel, Holded");
    assert.equal(tools.multiple, true);
    assert.deepEqual(tools.options.map((option) => option.value), ["excel", "holded"]);
  });

  it("offers no options on fields the review screen doesn't let the rep edit", () => {
    const [note] = changesFrom([
      { field_name: "description", field_label: "Note", new_value: "x", options: [{ value: "x", label: "X" }] },
    ]);
    assert.deepEqual(note.options, []);
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

describe("withEdits", () => {
  const proposed = [
    { field_name: "lifecyclestage", field_label: "Stage", object_type: "contacts", new_value: "lead", options: [{ value: "lead" }, { value: "customer" }] },
    { field_name: "tools", field_label: "Tools", object_type: "companies", new_value: "excel", multiple: true, options: [{ value: "excel" }, { value: "holded" }] },
    { field_name: "jobtitle", field_label: "Job title", object_type: "contacts", new_value: "CEO" },
  ];

  it("writes the option the rep picked, and several for a checkbox list", () => {
    const next = withEdits(proposed, { "contacts:lifecyclestage": "customer", "companies:tools": "excel;holded" });
    assert.deepEqual(next.map((update) => update.new_value), ["customer", "excel;holded", "CEO"]);
  });

  it("ignores a pick outside the field's options", () => {
    const next = withEdits(proposed, { "contacts:lifecyclestage": "made-up" });
    assert.deepEqual(next.map((update) => update.new_value), ["lead", "excel", "CEO"]);
  });

  it("writes text typed over a free-text value, trimmed; never blank", () => {
    assert.equal(withEdits(proposed, { "contacts:jobtitle": "  Founder  & CEO " })[2].new_value, "Founder & CEO");
    assert.equal(withEdits(proposed, { "contacts:jobtitle": "   " })[2].new_value, "CEO");
  });

  it("takes only a number for a number field, and nothing typed for dates or the note-made description", () => {
    const fields = [
      { field_name: "amount", object_type: "deals", field_type: "number", new_value: "5000" },
      { field_name: "closedate", object_type: "deals", field_type: "date", new_value: "2026-11-01" },
      { field_name: "description", object_type: "deals", new_value: "From the note" },
    ];
    assert.deepEqual(withEdits(fields, { "deals:amount": "7500", "deals:closedate": "tomorrow", "deals:description": "typed" }).map((u) => u.new_value), ["7500", "2026-11-01", "From the note"]);
    assert.equal(withEdits(fields, { "deals:amount": "about 7k" })[0].new_value, "5000");
  });
});

describe("summaryLines", () => {
  it("turns the note's markdown into a few plain lines", () => {
    assert.equal(summaryLines("## Call\n- **Pain:** 6 h a week\n\n* Budget 12k\n1. Send proposal"), "Call\nPain: 6 h a week\nBudget 12k\nSend proposal");
    assert.equal(summaryLines("a\nb\nc", 2), "a\nb");
    assert.equal(summaryLines("  "), null);
  });

  it("keeps bold at the start of a line from leaving a star behind", () => {
    assert.equal(summaryLines("**Resultado:** Quedan en hablar.\n**Situación:** 8 comerciales"), "Resultado: Quedan en hablar.\nSituación: 8 comerciales");
  });
});

describe("noteMarkdown", () => {
  const original = "**Resultado:** Quedan en hablar.\n## Situación\n- 8 comerciales\n- Usan **Gong**";
  it("keeps the markdown of the lines the rep left as they were", () => {
    assert.equal(noteMarkdown(summaryLines(original)!, original), "**Resultado:** Quedan en hablar.\n\n## Situación\n\n- 8 comerciales\n\n- Usan **Gong**");
  });
  it("writes a changed or new line as plain text, one per line", () => {
    assert.equal(
      noteMarkdown("Resultado: Reunión el martes.\nSituación\n8 comerciales\n\nPiden precio", original),
      "Resultado: Reunión el martes.\n\n## Situación\n\n- 8 comerciales\n\nPiden precio",
    );
    assert.equal(noteMarkdown("Una nota", null), "Una nota");
  });
});

describe("emailFrom", () => {
  it("shows a draft that exists, or that is being written", () => {
    assert.deepEqual(emailFrom({ status: "ready", recipientName: "Marta" }), { state: "ready", to: "Marta", subject: null, preview: null });
    assert.deepEqual(emailFrom({ status: "generating", recipientName: "Marta" }), { state: "writing", to: "Marta", subject: null, preview: null });
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
