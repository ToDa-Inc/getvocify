import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  callTypeFrom,
  changesFrom,
  crmForType,
  crmFor,
  defaultKept,
  emailFrom,
  leadStatusUpdate,
  meetingFrom,
  noteMarkdown,
  pendingItems,
  pollDelayMs,
  retypedTo,
  summaryLines,
  withEdits,
  withLeadStatus,
  type PostCall,
  newTasksFrom,
  withAddedTasks,
  tasksForApprove,
  taskEditsFrom,
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
      { key: "contacts:hs_lead_status", label: "Lead status", object: "contact", from: "NEW", to: "IN_PROGRESS", value: "IN_PROGRESS", options: [], multiple: false, editable: true, check: false, when: null, whenSuggested: false },
      { key: "deals:amount", label: "Amount", object: "deal", from: null, to: "196", value: "196", options: [], multiple: false, editable: true, check: true, when: null, whenSuggested: false },
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

  it("gives a task its day and hour, and says when the day is only a suggestion", () => {
    const [timed, suggested, field] = changesFrom([
      { object_type: "task", field_name: "next_step_task_0", field_label: "Next Step (Task)", new_value: "Llamar a Ana", due_at: "2026-10-20T18:30:00+02:00" },
      { object_type: "task", field_name: "next_step_task_1", field_label: "Next Step 2 (Task)", new_value: "Enviar la propuesta", due_at: "2026-10-17T09:00:00+02:00", due_date_inferred: true },
      { object_type: "contacts", field_name: "jobtitle", field_label: "Job title", new_value: "CRO", due_at: "2026-10-17T09:00:00+02:00" },
    ]);
    assert.match(timed.when ?? "", /Tue 20 Oct,? \d{2}:\d{2}/);
    assert.equal(timed.whenSuggested, false);
    assert.match(suggested.when ?? "", /Sat 17 Oct,? \d{2}:\d{2}/);
    assert.equal(suggested.whenSuggested, true);
    assert.equal(field.when, null, "only a task has a day and hour");
  });

  it("ticks every change: a flagged one is written too unless the rep unticks it", () => {
    const changes = changesFrom([
      { field_name: "a", field_label: "A", new_value: "x", extraction_confidence: 0.95 },
      { field_name: "b", field_label: "B", new_value: "y", extraction_confidence: 0.4 },
    ]);
    assert.deepEqual(defaultKept(changes), ["deals:a", "deals:b"]);
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
    assert.equal(pollDelayMs(0), 700);
    assert.equal(pollDelayMs(7), 700);
    assert.equal(pollDelayMs(8), 1500);
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

describe("lead status offered on every call", () => {
  const schema = [
    { name: "email", label: "Email" },
    { name: "hs_lead_status", label: "Lead Status", options: [{ label: "New", value: "NEW" }, { label: "Connected", value: "CONNECTED" }] },
  ];

  it("is the CRM's own field with its options, nothing chosen", () => {
    const offer = leadStatusUpdate(schema);
    assert.equal(offer?.field_name, "hs_lead_status");
    assert.equal(offer?.object_type, "contacts");
    assert.equal(offer?.new_value, "");
    assert.equal(offer?.options?.length, 2);
  });

  it("is absent when the CRM has no such field or no options", () => {
    assert.equal(leadStatusUpdate([{ name: "email" }]), null);
    assert.equal(leadStatusUpdate([{ name: "hs_lead_status", options: [] }]), null);
    assert.equal(leadStatusUpdate(null), null);
  });

  it("makes a card that can save even when the call proposed nothing", () => {
    const proposed = withLeadStatus([], leadStatusUpdate(schema));
    const crm = crmFor({ status: "pending_review", hubspotContactId: "42" }, proposed);
    assert.equal(crm.stage, "ready");
    assert.equal(crm.canApprove, true);
    assert.equal(crm.changes.length, 1);
    assert.equal(crm.changes[0].pending, true);
    assert.equal(crm.changes[0].key, "contacts:hs_lead_status");
  });

  it("leaves the call's own lead status alone", () => {
    const own = { field_name: "hs_lead_status", object_type: "contacts", current_value: "NEW", new_value: "CONNECTED", options: [{ value: "CONNECTED", label: "Connected" }] };
    const proposed = withLeadStatus([own], leadStatusUpdate(schema));
    assert.equal(proposed.length, 1);
    assert.equal(changesFrom(proposed)[0].pending, undefined);
  });

  it("takes the value the rep picks", () => {
    const proposed = withLeadStatus([], leadStatusUpdate(schema));
    const picked = withEdits(proposed, { "contacts:hs_lead_status": "CONNECTED" });
    assert.equal(picked[0].new_value, "CONNECTED");
    assert.equal(withEdits(proposed, { "contacts:hs_lead_status": "NOPE" })[0].new_value, "");
  });
});

describe("tasks added in the island", () => {
  it("keeps a title with a real day and drops the rest", () => {
    const tasks = newTasksFrom([{ title: "  Send   the proposal ", due: "2026-10-20" }, { title: "", due: "2026-10-20" }, { title: "No day" }, { title: "Bad day", due: "2026-13-40" }, "x"]);
    assert.deepEqual(tasks, [{ title: "Send the proposal", due: "2026-10-20" }]);
    assert.deepEqual(newTasksFrom(undefined), []);
  });

  it("puts them after the call's steps, each with its day", () => {
    const out = withAddedTasks({ nextSteps: ["Call back"], raw_extraction: { nextStepSchedules: ["2026-10-21"] } }, [{ title: "Send the proposal", due: "2026-10-20" }]);
    assert.deepEqual(out, { nextSteps: ["Call back", "Send the proposal"], nextStepSchedules: ["2026-10-21", "2026-10-20"] });
  });

  it("pads the days of steps that had none, and leaves the extraction alone when nothing was added", () => {
    const out = withAddedTasks({ nextSteps: ["A", "B"] }, [{ title: "C", due: "2026-10-20" }]);
    assert.deepEqual(out.nextStepSchedules, ["", "", "2026-10-20"]);
    assert.deepEqual(withAddedTasks({ nextSteps: ["A"] }, []), { nextSteps: ["A"] });
  });
});

describe("tasks the rep moved or added in the island", () => {
  const task = (n: number, value: string, due: string) => ({ field_name: `next_step_task_${n}`, object_type: "task", new_value: value, due_date: due, field_label: "Task", current_value: null, extraction_confidence: 0.9 });
  const proposed = [task(0, "Enviar el caso", "2026-10-21"), task(1, "Llamar a Ana", "2026-10-22")];

  it("keeps the proposed days, and marks the one the rep moved with its new day and hour", () => {
    const out = tasksForApprove({ nextSteps: [] }, proposed, [], { "task:next_step_task_1": { due: "2026-10-30", time: "15:30" } }, []);
    assert.deepEqual(out.nextSteps, ["Enviar el caso", "Llamar a Ana"]);
    assert.deepEqual(out.nextStepSchedules, ["2026-10-21", "2026-10-30 a las 15:30"]);
    assert.deepEqual(out.reviewedTaskDates, ["", "2026-10-30 a las 15:30"]);
  });

  it("writes a re-worded task from its new text, on the day and hour the call gave it", () => {
    const timed = [{ ...task(0, "Llamar a Ana", "2026-10-29"), due_at: "2026-10-29T18:00:00+01:00" }];
    const out = tasksForApprove({ nextSteps: [] }, timed, [], { "task:next_step_task_0": { title: "Llamar a Ana por el precio" } }, []);
    assert.deepEqual(out.nextSteps, ["Llamar a Ana por el precio"]);
    assert.deepEqual(out.nextStepSchedules, ["2026-10-29 a las 18:00"]);
    assert.deepEqual(out.reviewedTaskDates, [""]);
  });

  it("leaves out a task the rep unticked, and adds theirs after with the hour they chose", () => {
    const out = tasksForApprove({ nextSteps: [] }, proposed, ["task:next_step_task_0"], {}, [{ title: "Mandar contrato", due: "2026-10-28", time: "09:00" }]);
    assert.deepEqual(out.nextSteps, ["Llamar a Ana", "Mandar contrato"]);
    assert.deepEqual(out.nextStepSchedules, ["2026-10-22", "2026-10-28 a las 09:00"]);
    assert.deepEqual(out.reviewedTaskDates, ["", ""]);
  });

  it("keeps the extraction's steps when the call proposed no task rows", () => {
    const out = tasksForApprove({ nextSteps: ["Call back"] }, [], [], {}, [{ title: "Send it", due: "2026-10-20" }]);
    assert.deepEqual(out.nextSteps, ["Call back", "Send it"]);
  });

  it("takes only real days and hours from the island", () => {
    assert.deepEqual(newTasksFrom([{ title: "A", due: "2026-10-20", time: "7:5" }]), [{ title: "A", due: "2026-10-20" }]);
    assert.deepEqual(newTasksFrom([{ title: "A", due: "2026-10-20", time: "07:05" }]), [{ title: "A", due: "2026-10-20", time: "07:05" }]);
    assert.deepEqual(taskEditsFrom({ k: { due: "2026-13-40" }, j: { due: "2026-10-20" }, t: { title: "  Nuevo   texto " } }), { j: { due: "2026-10-20" }, t: { title: "Nuevo texto" } });
  });
});
