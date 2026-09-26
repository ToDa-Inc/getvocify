import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { afterActionError, composeHome, HOME_CAP, NEEDS_OK_VISIBLE, REVIEW_LIMIT } from "./home.js";

const NOW = Date.parse("2026-09-29T08:30:00+02:00");
const TZ = "Europe/Madrid";

function view(items, extra = {}) {
  return {
    items,
    pulse: null,
    folded_count: 0,
    generated_at: "2026-09-29T08:29:00+02:00",
    coverage: { intelligence: "complete", crm_tasks: "complete" },
    ...extra,
  };
}

function card(n, extra = {}) {
  return {
    type: "commitment_due",
    dedupe_key: `commitment:m${n}:call:2026-09-29`,
    id: `sig-${n}`,
    version: 1,
    status: "pending",
    contact_id: `c${n}`,
    contact_name: `Contacto ${n}`,
    company_name: null,
    reason: "Pidió que le llamaras.",
    detail: null,
    origins: ["detected"],
    supporting: [],
    ...extra,
  };
}

const meeting = (n, extra = {}) => card(n, {
  type: "meeting_today",
  dedupe_key: `meeting:${n}`,
  reason: `Demo con Contacto ${n}`,
  due_at: "2026-09-29T11:30:00+02:00",
  precision: "time",
  ...extra,
});

const confirmation = (n, extra = {}) => card(n, {
  type: "confirm_pending",
  dedupe_key: `confirm:${n}`,
  reason: `Confirma: reunión jue 1 oct, 11:00 con Contacto ${n}`,
  detail: "Etapa → Meeting booked",
  ...extra,
});

const priority = (n, reason = "no_calls_logged") => ({
  id: `conn:c${n}:`,
  connection_id: "conn",
  contact_id: `c${n}`,
  contact_name: `Prioridad ${n}`,
  reason,
  next_action: null,
  coverage: "complete",
});

const priorities = (items, extra = {}) => ({
  items,
  coverage: "complete",
  title: items.length ? null : "title_none_now",
  action: items.length ? null : "open_contacts",
  ...extra,
});

const followup = (n, status = "ready", extra = {}) => ({
  memo_id: `f${n}`,
  contact_id: `c${n}`,
  contact_name: `Follow ${n}`,
  company_name: null,
  subject: status === "ready" ? `Asunto ${n}` : null,
  status,
  generated_at: "2026-09-28T10:00:00+00:00",
  ...extra,
});

const review = (n, extra = {}) => ({
  id: `r${n}`,
  status: "pending_review",
  extraction: { contactName: `Revisión ${n}` },
  ...extra,
});

function input(overrides = {}) {
  return {
    today: view([]),
    todayError: false,
    todayStale: false,
    acted: [],
    priorities: priorities([]),
    followups: [],
    reviews: [],
    upcoming: [],
    done: [],
    connected: true,
    role: "member",
    crm: "HubSpot",
    now: NOW,
    locale: "es-ES",
    timeZone: TZ,
    ...overrides,
  };
}

const doneCall = { kind: "call", contact_name: "A", at: "2026-09-29T08:00:00+02:00", memo_id: "m1" };

const ids = (home) => home.sections.map((section) => section.id);
const section = (home, id) => home.sections.find((entry) => entry.id === id);
const callContacts = (home) => section(home, "calls").items.map((entry) => entry.item.contact_id);

describe("composeHome sections", () => {
  it("orders sections and leaves empty ones out", () => {
    const full = composeHome(input({
      today: view([meeting(1), confirmation(2), card(3)]),
      upcoming: [{ memo_id: "u1", contact_id: "c4", contact_name: "A", company_name: null, text: "Enviar la propuesta", due_at: "2026-09-30T10:00:00+02:00", precision: "time", crm_task_id: null }],
      done: [{ kind: "call", contact_name: "Marina Ortiz", at: "2026-09-29T08:00:00+02:00", memo_id: "d1" }],
    }));
    assert.deepEqual(ids(full), ["meetings", "needs_ok", "calls", "upcoming", "done"]);

    const sparse = composeHome(input({
      today: view([card(1)]),
      done: [{ kind: "call", contact_name: "Marina Ortiz", at: "2026-09-29T08:00:00+02:00", memo_id: "d1" }],
    }));
    assert.deepEqual(ids(sparse), ["calls", "done"]);
  });

  it("caps Hoy at seven across meetings, confirmations and calls", () => {
    const calls = [3, 4, 5, 6, 7, 8].map((n) => card(n + 10));
    const home = composeHome(input({
      today: view([meeting(1), meeting(2), confirmation(3), confirmation(4), ...calls]),
    }));
    assert.equal(HOME_CAP, 7);
    assert.equal(section(home, "meetings").items.length, 2);
    assert.deepEqual(section(home, "needs_ok").rows.map((row) => row.kind), ["confirm", "confirm"]);
    assert.equal(section(home, "calls").items.length, 3);
    assert.equal(section(home, "calls").folded, 3);
  });

  it("groups three or more confirmations into one row that counts once", () => {
    const calls = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => card(n + 20));
    const home = composeHome(input({
      today: view([confirmation(1), confirmation(2), confirmation(3), confirmation(4), ...calls]),
    }));
    const rows = section(home, "needs_ok").rows;
    assert.equal(rows.length, 1);
    assert.equal(rows[0].kind, "confirm_group");
    assert.equal(rows[0].count, 4);
    assert.equal(rows[0].items.length, 4);
    assert.equal(section(home, "calls").items.length, 6);
    assert.equal(section(home, "calls").folded, 2);
  });

  it("dedupes by contact so /today wins over /contact-priorities", () => {
    const home = composeHome(input({
      today: view([card(1)]),
      priorities: priorities([
        priority(1, "pain_agree_next_step"),
        priority(9, "pain_agree_next_step"),
        priority(8, "no_calls_logged"),
      ]),
    }));
    const entries = section(home, "calls").items;
    assert.deepEqual(entries.map((entry) => [entry.source, entry.item.contact_id]), [
      ["today", "c1"],
      ["priority", "c9"],
      ["priority", "c8"],
    ]);
    assert.equal(entries[1].item.type, "pain_confirmed");
    assert.equal(entries[1].item.reason, "pain_agree_next_step");
    assert.equal(entries[1].item.id, null);
    assert.equal(entries[2].item.type, "uncalled");
  });

  it("keeps only confirmed pain and never-called contacts from /contact-priorities", () => {
    const home = composeHome(input({
      priorities: priorities([
        priority(1, "followup_pending"),
        priority(2, "scheduled_no_early_call"),
        priority(3, "history_partial"),
        priority(4, "no_calls_logged"),
      ]),
    }));
    assert.deepEqual(callContacts(home), ["c4"]);
  });

  it("shows seven of forty signals and folds thirty-three", () => {
    const seven = [1, 2, 3, 4, 5, 6, 7].map((n) => card(n));
    const home = composeHome(input({ today: view(seven, { folded_count: 33 }) }));
    assert.equal(section(home, "calls").items.length, 7);
    assert.equal(section(home, "calls").folded, 33);
  });

  it("does not fold CRM tasks the home never paints", () => {
    const tasks = [1, 2, 3, 4].map((n) => ({ ...card(n + 50), type: "manual_task", id: null, dedupe_key: null }));
    const home = composeHome(input({ today: view([card(1), card(2), card(3), ...tasks], { folded_count: 6 }) }));
    assert.deepEqual(callContacts(home), ["c1", "c2", "c3"]);
    assert.equal(section(home, "calls").folded, 0);
  });
});

describe("composeHome needs your OK", () => {
  it("shows three rows and folds the rest, follow-ups before reviews", () => {
    const home = composeHome(input({
      followups: [followup(1), followup(2), followup(3, "generating"), followup(4, "unavailable")],
      reviews: [review(1), review(2)],
    }));
    const needs = section(home, "needs_ok");
    assert.equal(NEEDS_OK_VISIBLE, 3);
    assert.equal(needs.rows.length, 6);
    assert.equal(needs.shown.length, 3);
    assert.equal(needs.more, 3);
    assert.deepEqual(needs.rows.map((row) => row.kind), ["followup", "followup", "followup", "followup", "review", "review"]);
  });

  it("does not count follow-ups and reviews against the cap of seven", () => {
    const seven = [1, 2, 3, 4, 5, 6, 7].map((n) => card(n));
    const home = composeHome(input({ today: view(seven), followups: [followup(1)], reviews: [review(1)] }));
    assert.equal(section(home, "calls").items.length, 7);
    assert.equal(section(home, "calls").folded, 0);
  });

  it("opens a ready draft, gives a draft being written no action and a failed one only Open", () => {
    const home = composeHome(input({
      followups: [followup(1), followup(2, "generating"), followup(3, "unavailable")],
    }));
    const [ready, writing, failed] = section(home, "needs_ok").rows;
    assert.deepEqual(
      { kind: ready.kind, memoId: ready.memoId, name: ready.name, subject: ready.subject, status: ready.status, action: ready.action },
      { kind: "followup", memoId: "f1", name: "Follow 1", subject: "Asunto 1", status: "ready", action: "open" },
    );
    assert.equal(writing.status, "generating");
    assert.equal(writing.action, null);
    assert.equal(failed.status, "unavailable");
    assert.equal(failed.action, "open");
  });

  it("names the contact of a conversation waiting for review and opens its memo", () => {
    const home = composeHome(input({ reviews: [review(1), review(2, { extraction: null })] }));
    const [named, unnamed] = section(home, "needs_ok").rows;
    assert.deepEqual(
      { kind: named.kind, memoId: named.memoId, name: named.name, action: named.action },
      { kind: "review", memoId: "r1", name: "Revisión 1", action: "review" },
    );
    assert.equal(unnamed.name, null);
  });
});

describe("composeHome coming up and done today", () => {
  it("marks CRM tasks and labels tomorrow and later days", () => {
    const home = composeHome(input({
      upcoming: [
        { memo_id: "u1", contact_id: "c1", contact_name: "A", company_name: null, text: "Enviar la propuesta", due_at: "2026-09-30T10:00:00+02:00", precision: "time", crm_task_id: "t-1" },
        { memo_id: "u2", contact_id: "c2", contact_name: "B", company_name: null, text: "Mandar el caso", due_at: "2026-10-05T00:00:00+02:00", precision: "date", crm_task_id: null },
      ],
    }));
    const rows = section(home, "upcoming").rows;
    assert.deepEqual(rows.map((row) => [row.text, row.inCrm, row.when]), [
      ["Enviar la propuesta", true, "Mañana"],
      ["Mandar el caso", false, "Lun 5 oct"],
    ]);
  });

  it("keeps only the call when a contact also has a resolved card, and counts what it shows", () => {
    const home = composeHome(input({
      done: [
        { kind: "call", contact_name: "Marina Ortiz", at: "2026-09-29T09:00:00+02:00", memo_id: "d1" },
        { kind: "followup", contact_name: "Jordi Puig", at: "2026-09-29T08:15:00+02:00", memo_id: "d2" },
        { kind: "signal", contact_name: " marina  ortiz ", at: "2026-09-29T08:00:00+02:00", memo_id: "d3" },
        { kind: "signal", contact_name: null, at: "2026-09-29T07:50:00+02:00", memo_id: null },
        { kind: "call", contact_name: null, at: "2026-09-29T07:40:00+02:00", memo_id: "d5" },
        { kind: "meeting_note", contact_name: "Otro", at: "2026-09-29T07:30:00+02:00", memo_id: "d6" },
      ],
    }));
    const done = section(home, "done");
    assert.deepEqual(done.rows.map((row) => [row.kind, row.name, row.time]), [
      ["call", "Marina Ortiz", "09:00"],
      ["followup", "Jordi Puig", "08:15"],
      ["signal", null, "07:50"],
      ["call", null, "07:40"],
    ]);
    assert.equal(done.count, 4);
  });
});

describe("composeHome pulse", () => {
  const calls = [
    { kind: "call", contact_name: "A", at: "2026-09-29T08:00:00+02:00", memo_id: "m1" },
    { kind: "call", contact_name: "B", at: "2026-09-29T08:10:00+02:00", memo_id: "m2" },
    { kind: "call", contact_name: "C", at: "2026-09-29T08:20:00+02:00", memo_id: "m3" },
    { kind: "followup", contact_name: "D", at: "2026-09-29T08:25:00+02:00", memo_id: "m4" },
  ];

  it("says all calls are saved only when none waits for review", () => {
    assert.deepEqual(composeHome(input({ done: calls })).pulse, { calls: 3, savedTo: "HubSpot" });
    assert.deepEqual(composeHome(input({ done: calls, reviews: [review(1, { id: "m2" })] })).pulse, { calls: 3, savedTo: null });
  });

  it("does not claim saved when the review read is full, failed, or there is no CRM", () => {
    const full = Array.from({ length: REVIEW_LIMIT }, (_, n) => review(n + 10));
    assert.equal(composeHome(input({ done: calls, reviews: full })).pulse.savedTo, null);
    assert.equal(composeHome(input({ done: calls, reviews: null })).pulse.savedTo, null);
    assert.equal(composeHome(input({ done: calls, crm: null })).pulse.savedTo, null);
    assert.equal(composeHome(input({ done: calls, connected: false })).pulse.savedTo, null);
  });

  it("does not claim saved for a call without its conversation", () => {
    const orphan = [...calls, { kind: "call", contact_name: "E", at: "2026-09-29T08:28:00+02:00", memo_id: null }];
    assert.deepEqual(composeHome(input({ done: orphan })).pulse, { calls: 4, savedTo: null });
  });

  it("has no pulse without calls today", () => {
    assert.equal(composeHome(input({ done: [calls[3]] })).pulse, null);
    assert.equal(composeHome(input({ done: null })).pulse, null);
  });
});

describe("composeHome states", () => {
  it("shows only the loading state while /today has not answered", () => {
    const home = composeHome(input({ today: null, followups: [followup(1)], done: [doneCall] }));
    assert.equal(home.state, "loading");
    assert.deepEqual(home.sections, []);
  });

  it("keeps the other sections when /today fails", () => {
    const home = composeHome(input({
      today: null,
      todayError: true,
      followups: [followup(1)],
      upcoming: [{ memo_id: "u1", contact_id: "c1", contact_name: "A", company_name: null, text: "Enviar", due_at: "2026-09-30T10:00:00+02:00", precision: "time", crm_task_id: null }],
      done: [doneCall],
    }));
    assert.equal(home.state, "error");
    assert.deepEqual(ids(home), ["needs_ok", "upcoming", "done"]);
  });

  it("shows only /today cards when /contact-priorities fails, without an error", () => {
    const home = composeHome(input({ today: view([card(1), card(2)]), priorities: null }));
    assert.equal(home.state, "day");
    assert.deepEqual(callContacts(home), ["c1", "c2"]);
  });

  it("asks a member to have the CRM connected and lets an admin connect it", () => {
    const member = composeHome(input({ connected: false, crm: null }));
    assert.equal(member.state, "connect");
    assert.equal(member.canManage, false);
    const admin = composeHome(input({ connected: false, crm: null, role: "admin" }));
    assert.equal(admin.state, "connect");
    assert.equal(admin.canManage, true);
    const withCards = composeHome(input({ connected: false, crm: null, today: view([card(1)]) }));
    assert.equal(withCards.state, "day");
  });

  it("fills who to call with never-called contacts when there are no conversations yet", () => {
    const home = composeHome(input({ priorities: priorities([priority(1), priority(2)]) }));
    assert.equal(home.state, "day");
    assert.deepEqual(section(home, "calls").items.map((entry) => entry.item.type), ["uncalled", "uncalled"]);
  });

  it("explains missing assignments to a member and offers mapping to an admin", () => {
    const empty = priorities([], { title: "title_no_assigned", action: "review_assignment" });
    const member = composeHome(input({ priorities: empty }));
    assert.equal(member.state, "no_assigned");
    assert.equal(member.canManage, false);
    const admin = composeHome(input({ priorities: { ...empty, action: "map_owners" }, role: "owner" }));
    assert.equal(admin.state, "no_assigned");
    assert.equal(admin.canManage, true);
  });

  it("says nothing is urgent and keeps coming up and done today when nothing is pending", () => {
    const home = composeHome(input({
      upcoming: [{ memo_id: "u1", contact_id: "c1", contact_name: "A", company_name: null, text: "Enviar", due_at: "2026-09-30T10:00:00+02:00", precision: "time", crm_task_id: null }],
      done: [doneCall],
    }));
    assert.equal(home.state, "clear");
    assert.deepEqual(ids(home), ["upcoming", "done"]);
  });

  it("marks a partial read with its time and never calls it clear", () => {
    const partial = { intelligence: "complete", crm_tasks: "partial" };
    const withCards = composeHome(input({ today: view([card(1)], { coverage: partial }) }));
    assert.equal(withCards.state, "day");
    assert.equal(withCards.incompleteAt, "08:29");
    const empty = composeHome(input({ today: view([], { coverage: partial }) }));
    assert.equal(empty.state, "day");
    assert.equal(empty.incompleteAt, "08:29");
    const stale = composeHome(input({ today: view([card(1)]), todayStale: true }));
    assert.equal(stale.incompleteAt, "08:29");
    assert.equal(composeHome(input({ today: view([card(1)]) })).incompleteAt, null);
  });
});

describe("composeHome meetings", () => {
  it("labels a meeting without a time, keeps a moved one's text and dims a past one", () => {
    const home = composeHome(input({
      today: view([
        meeting(1),
        meeting(2, { precision: "date", due_at: "2026-09-29T00:00:00+02:00" }),
        meeting(3, { detail: "acordada el 24 sep" }),
        meeting(4, { due_at: "2026-09-29T08:00:00+02:00" }),
        meeting(5, { due_at: "2026-09-29T08:00:00+02:00", memo_id: "captured" }),
      ]),
    }));
    const items = section(home, "meetings").items;
    assert.deepEqual(items.map((entry) => [entry.item.contact_id, entry.time, entry.past]), [
      ["c1", "11:30", false],
      ["c2", null, false],
      ["c3", "11:30", false],
      ["c4", "08:00", true],
    ]);
    assert.equal(items[2].item.detail, "acordada el 24 sep");
  });
});

describe("composeHome refresh", () => {
  it("drops a confirmation settled elsewhere and a contact deleted in the CRM on the next read", () => {
    const before = composeHome(input({ today: view([confirmation(1), card(2), card(3)]) }));
    assert.equal(section(before, "needs_ok").rows.length, 1);
    assert.deepEqual(callContacts(before), ["c2", "c3"]);
    const after = composeHome(input({ today: view([card(3)]) }));
    assert.equal(section(after, "needs_ok"), undefined);
    assert.deepEqual(callContacts(after), ["c3"]);
  });
});

describe("composeHome actions", () => {
  const dismissed = (extra = {}) => card(1, {
    status: "dismissed",
    version: 2,
    undo_deadline: new Date(NOW + 3000).toISOString(),
    last_action_request_id: "req-1",
    ...extra,
  });

  it("never lets an older local result beat /today", () => {
    const home = composeHome(input({
      today: view([card(1, { version: 3 })]),
      acted: [dismissed()],
    }));
    const [entry] = section(home, "calls").items;
    assert.equal(entry.item.status, "pending");
    assert.equal(entry.item.version, 3);
  });

  it("shows a newer local result while its undo lasts, then the card leaves", () => {
    const today = view([card(1), card(2)]);
    const during = composeHome(input({ today, acted: [dismissed()] }));
    assert.equal(section(during, "calls").items[0].item.status, "dismissed");
    const after = composeHome(input({ today, acted: [dismissed()], now: NOW + 6000 }));
    assert.deepEqual(callContacts(after), ["c2"]);
  });

  it("keeps a dismissed card that left /today only for its undo window", () => {
    const today = view([card(2)]);
    assert.deepEqual(callContacts(composeHome(input({ today, acted: [dismissed()] }))), ["c2", "c1"]);
    assert.deepEqual(callContacts(composeHome(input({ today, acted: [dismissed()], now: NOW + 6000 }))), ["c2"]);
  });

  it("forgets the local result and reads /today again after a 409", () => {
    assert.deepEqual(
      afterActionError({ status: 409, data: { detail: { id: "sig-1", status: "dismissed", version: 4 } } }),
      { forget: "sig-1", refetch: true },
    );
    assert.deepEqual(
      afterActionError({ status: 409, data: { detail: { reason: "undo_expired", id: "sig-2", status: "dismissed", version: 5 } } }),
      { forget: "sig-2", refetch: true },
    );
    assert.deepEqual(afterActionError({ status: 409, data: {} }), { forget: null, refetch: true });
    assert.equal(afterActionError({ status: 500, data: {} }), null);
    assert.equal(afterActionError(new Error("offline")), null);

    const refetched = composeHome(input({ today: view([card(1, { status: "pending", version: 5 })]), acted: [] }));
    assert.equal(section(refetched, "calls").items[0].item.version, 5);
  });
});