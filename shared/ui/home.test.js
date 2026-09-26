import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  afterActionError,
  composeHome,
  FOLLOWUP_POLL_FOR_MS,
  FOLLOWUP_POLL_MS,
  followupPoll,
  HOME_CAP,
  HOME_WIDE_PX,
  holdOrder,
  homeRows,
  homeSelection,
  initialHomeSelection,
  NEEDS_OK_VISIBLE,
  REVIEW_LIMIT,
  selectedRow,
  snoozeUntil,
} from "./home.js";

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
    assert.deepEqual(home.folded, { count: 3, after: "calls" });
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
    assert.deepEqual(home.folded, { count: 2, after: "calls" });
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
    assert.deepEqual(home.folded, { count: 33, after: "calls" });
  });

  it("keeps the folded line when seven meetings use the whole budget", () => {
    const meetings = [1, 2, 3, 4, 5, 6, 7].map((n) => meeting(n));
    const home = composeHome(input({ today: view([...meetings, card(11), card(12), card(13)]) }));
    assert.deepEqual(ids(home), ["meetings"]);
    assert.deepEqual(home.folded, { count: 3, after: "meetings" });
  });

  it("adds /today's folded count when seven meetings fill Hoy", () => {
    const meetings = [1, 2, 3, 4, 5, 6, 7].map((n) => meeting(n));
    const home = composeHome(input({ today: view(meetings, { folded_count: 12 }) }));
    assert.deepEqual(ids(home), ["meetings"]);
    assert.deepEqual(home.folded, { count: 12, after: "meetings" });
  });

  it("puts the folded line under the confirmations when they are the last Hoy cards", () => {
    const meetings = [1, 2, 3, 4, 5, 6].map((n) => meeting(n));
    const home = composeHome(input({ today: view([...meetings, confirmation(7), confirmation(8)]) }));
    assert.equal(section(home, "needs_ok").rows.length, 1);
    assert.deepEqual(home.folded, { count: 1, after: "needs_ok" });
  });

  it("does not fold CRM tasks the home never paints", () => {
    const tasks = [1, 2, 3, 4].map((n) => ({ ...card(n + 50), type: "manual_task", id: null, dedupe_key: null }));
    const home = composeHome(input({ today: view([card(1), card(2), card(3), ...tasks], { folded_count: 6 }) }));
    assert.deepEqual(callContacts(home), ["c1", "c2", "c3"]);
    assert.equal(home.folded, null);
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
    assert.equal(home.folded, null);
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

  it("matches a call and a resolved card by contact id when both have one, by name otherwise", () => {
    const home = composeHome(input({
      done: [
        { kind: "call", contact_name: "Marina Ortiz", contact_id: "c1", at: "2026-09-29T09:00:00+02:00", memo_id: "d1" },
        { kind: "signal", contact_name: "M. Ortiz", contact_id: "c1", at: "2026-09-29T08:50:00+02:00", memo_id: "d2" },
        { kind: "call", contact_name: "Ana Gil", contact_id: "c2", at: "2026-09-29T08:40:00+02:00", memo_id: "d3" },
        { kind: "signal", contact_name: "Ana Gil", contact_id: "c9", at: "2026-09-29T08:30:00+02:00", memo_id: "d4" },
        { kind: "call", contact_name: "Luis Mora", contact_id: null, at: "2026-09-29T08:20:00+02:00", memo_id: "d5" },
        { kind: "signal", contact_name: "luis mora", contact_id: "c5", at: "2026-09-29T08:10:00+02:00", memo_id: "d6" },
      ],
    }));
    assert.deepEqual(section(home, "done").rows.map((row) => [row.kind, row.name]), [
      ["call", "Marina Ortiz"],
      ["call", "Ana Gil"],
      ["signal", "Ana Gil"],
      ["call", "Luis Mora"],
    ]);
  });
});

describe("followupPoll", () => {
  it("polls every five seconds while a draft is being written, for two minutes at most", () => {
    const writing = [followup(1, "generating"), followup(2)];
    assert.equal(FOLLOWUP_POLL_MS, 5000);
    assert.equal(FOLLOWUP_POLL_FOR_MS, 120_000);
    assert.deepEqual(followupPoll(writing, null, NOW), { interval: 5000, since: NOW });
    assert.deepEqual(followupPoll(writing, NOW - 60_000, NOW), { interval: 5000, since: NOW - 60_000 });
    assert.deepEqual(followupPoll(writing, NOW - 120_000, NOW), { interval: false, since: NOW - 120_000 });
  });

  it("stops and forgets the clock when nothing is being written", () => {
    assert.deepEqual(followupPoll([followup(1), followup(2, "unavailable")], NOW - 30_000, NOW), { interval: false, since: null });
    assert.deepEqual(followupPoll(undefined, null, NOW), { interval: false, since: null });
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
    const home = composeHome(input({ today: undefined, followups: [followup(1)], done: [doneCall] }));
    assert.equal(home.state, "loading");
    assert.deepEqual(home.sections, []);
  });

  it("keeps the other sections when /today fails", () => {
    const home = composeHome(input({
      today: null,
      followups: [followup(1)],
      upcoming: [{ memo_id: "u1", contact_id: "c1", contact_name: "A", company_name: null, text: "Enviar", due_at: "2026-09-30T10:00:00+02:00", precision: "time", crm_task_id: null }],
      done: [doneCall],
    }));
    assert.equal(home.state, "error");
    assert.deepEqual(ids(home), ["needs_ok", "upcoming", "done"]);
  });

  it("keeps the priority cards under who to call when /today fails", () => {
    const home = composeHome(input({ today: null, priorities: priorities([priority(1, "pain_agree_next_step"), priority(2)]) }));
    assert.equal(home.state, "error");
    assert.deepEqual(ids(home), ["calls"]);
    assert.deepEqual(section(home, "calls").items.map((entry) => [entry.source, entry.item.contact_id]), [
      ["priority", "c1"],
      ["priority", "c2"],
    ]);
  });

  it("does not say nothing is urgent or ask for the CRM until the reads that decide it have answered", () => {
    for (const pending of [{ priorities: undefined }, { followups: undefined }, { reviews: undefined }]) {
      const home = composeHome(input(pending));
      assert.equal(home.state, "day", JSON.stringify(Object.keys(pending)));
    }
    const integrations = composeHome(input({ connected: undefined, crm: null }));
    assert.equal(integrations.state, "day");
    assert.equal(composeHome(input({ connected: false, crm: null })).state, "connect");
    assert.equal(composeHome(input()).state, "clear");
  });

  it("does not say nothing is urgent when a read that decides it failed, and marks the day incomplete", () => {
    for (const failed of [{ priorities: null }, { followups: null }, { reviews: null }]) {
      const home = composeHome(input(failed));
      assert.equal(home.state, "day", JSON.stringify(Object.keys(failed)));
      assert.equal(home.incompleteAt, "08:29");
    }
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
  });

  it("leaves no local ghost after a 409 on a card another tab already settled", () => {
    const acted = [dismissed()];
    const today = view([card(2)]);
    assert.deepEqual(callContacts(composeHome(input({ today, acted }))), ["c2", "c1"]);
    const outcome = afterActionError({ status: 409, data: { detail: { id: "sig-1", status: "resolved", version: 3 } } });
    const forgotten = acted.filter((item) => item.id !== outcome.forget);
    assert.deepEqual(callContacts(composeHome(input({ today, acted: forgotten }))), ["c2"]);
  });
});
describe("home selection", () => {
  const home = (overrides) => composeHome(input(overrides));
  const keys = (rows) => rows.map((row) => row.key);
  const refresh = (state, rows, wide = true) => homeSelection(state, { type: "rows", rows, wide });
  const selectedKey = (state, rows) => selectedRow(state, rows)?.key ?? null;
  const day = home({
    today: view([meeting(1), confirmation(2), card(3), card(4)]),
    followups: [followup(5)],
    reviews: [review(6)],
    priorities: priorities([priority(7)]),
  });

  it("walks meetings, then Falta tu OK, then calls, in the order they are painted", () => {
    const rows = homeRows(day);
    assert.deepEqual(keys(rows), ["hoy:sig-1", "hoy:sig-2", "followup:f5", "review:r6", "hoy:sig-3", "hoy:sig-4", "priority:conn:c7:"]);
    assert.deepEqual(rows.map((row) => row.kind), ["meeting", "confirm", "followup", "review", "call", "call", "call"]);
    assert.deepEqual(rows.map((row) => row.contactId), ["c1", "c2", "c5", null, "c3", "c4", "c7"]);
  });

  it("skips the grouped confirmations and a card waiting on its undo", () => {
    const grouped = home({
      today: view([confirmation(1), confirmation(2), confirmation(3), card(4)]),
      acted: [{ ...card(5), status: "dismissed", version: 2, undo_deadline: new Date(NOW + 3000).toISOString() }],
    });
    assert.deepEqual(keys(homeRows(grouped)), ["hoy:sig-4"]);
    assert.deepEqual(keys(homeRows(grouped, { groupOpen: true })), ["hoy:sig-1", "hoy:sig-2", "hoy:sig-3", "hoy:sig-4"]);
  });

  it("walks the rows «{n} más» reveals only once it is open", () => {
    const many = home({ followups: [followup(1), followup(2), followup(3), followup(4)] });
    assert.deepEqual(keys(homeRows(many)), ["followup:f1", "followup:f2", "followup:f3"]);
    assert.deepEqual(keys(homeRows(many, { needsOkOpen: true })), ["followup:f1", "followup:f2", "followup:f3", "followup:f4"]);
  });

  it("selects the first call on a wide screen, even under meetings and Falta tu OK", () => {
    const rows = homeRows(day);
    assert.equal(HOME_WIDE_PX, 1280);
    assert.equal(selectedKey(refresh(initialHomeSelection, rows), rows), "hoy:sig-3");
    assert.equal(selectedRow(refresh(initialHomeSelection, rows), rows).item.contact_id, "c3");
  });

  it("selects nothing below 1280 px until the rep picks a row", () => {
    const rows = homeRows(day);
    const narrow = refresh(initialHomeSelection, rows, false);
    assert.equal(selectedKey(narrow, rows), null);
    assert.equal(selectedKey(homeSelection(narrow, { type: "select", key: "review:r6" }), rows), "review:r6");
  });

  it("selects the first row when there is nobody to call", () => {
    const rows = homeRows(home({ today: view([meeting(1)]), followups: [followup(2)] }));
    assert.equal(selectedKey(refresh(initialHomeSelection, rows), rows), "hoy:sig-1");
    assert.equal(selectedKey(refresh(initialHomeSelection, []), []), null);
  });

  it("stays unselected after Escape, whatever the next refresh brings", () => {
    const rows = homeRows(day);
    const cleared = homeSelection(refresh(initialHomeSelection, rows), { type: "exit" });
    assert.equal(selectedKey(cleared, rows), null);
    assert.equal(selectedKey(refresh(cleared, rows), rows), null);
    assert.equal(selectedKey(refresh(cleared, homeRows(home({ today: view([card(9)]) }))), rows), null);
  });

  it("moves with next and prev without wrapping; with nothing selected, down is the first row and up the last", () => {
    const rows = homeRows(day);
    const none = homeSelection(refresh(initialHomeSelection, rows), { type: "exit" });
    assert.equal(selectedKey(homeSelection(none, { type: "next" }), rows), "hoy:sig-1");
    assert.equal(selectedKey(homeSelection(none, { type: "prev" }), rows), "priority:conn:c7:");
    const first = homeSelection(none, { type: "next" });
    assert.equal(selectedKey(homeSelection(first, { type: "prev" }), rows), "hoy:sig-1");
    const last = homeSelection(none, { type: "prev" });
    assert.equal(selectedKey(homeSelection(last, { type: "next" }), rows), "priority:conn:c7:");
    assert.equal(selectedKey(homeSelection(first, { type: "next" }), rows), "hoy:sig-2");
  });

  it("skips to the next row, and past the last one leaves nothing selected as F06 does", () => {
    const rows = homeRows(day);
    const start = refresh(initialHomeSelection, rows);
    assert.equal(selectedKey(homeSelection(start, { type: "skip" }), rows), "hoy:sig-4");
    const last = homeSelection(start, { type: "select", key: "priority:conn:c7:" });
    const skipped = homeSelection(last, { type: "skip" });
    assert.equal(selectedKey(skipped, rows), null);
    assert.equal(selectedKey(refresh(skipped, rows), rows), null);
  });

  it("moves to the next row when the selected card is resolved, to the previous one at the end, and to nothing when none is left", () => {
    const before = home({ today: view([card(1), card(2), card(3)]) });
    const start = refresh(initialHomeSelection, homeRows(before));
    const resolvedAt = new Date(NOW + 4000).toISOString();
    const settle = (n) => ({ ...card(n), status: "dismissed", version: 2, undo_deadline: resolvedAt });

    const afterFirst = homeRows(home({ today: view([card(1), card(2), card(3)]), acted: [settle(1)] }));
    assert.equal(selectedKey(refresh(start, afterFirst), afterFirst), "hoy:sig-2");

    const atLast = homeSelection(start, { type: "select", key: "hoy:sig-3" });
    const afterLast = homeRows(home({ today: view([card(1), card(2), card(3)]), acted: [settle(3)] }));
    assert.equal(selectedKey(refresh(atLast, afterLast), afterLast), "hoy:sig-2");

    const only = refresh(initialHomeSelection, homeRows(home({ today: view([card(1)]) })));
    const nothing = homeRows(home({ today: view([card(1)]), acted: [settle(1)] }));
    assert.equal(selectedKey(refresh(only, nothing), nothing), null);
  });

  it("moves on when the selected contact disappears on refresh (deleted in the CRM)", () => {
    const start = homeSelection(refresh(initialHomeSelection, homeRows(home({ today: view([card(1), card(2), card(3)]) }))), {
      type: "select",
      key: "hoy:sig-2",
    });
    const gone = homeRows(home({ today: view([card(1), card(3), card(4)]) }));
    assert.equal(selectedKey(refresh(start, gone), gone), "hoy:sig-3");
    const tail = homeSelection(start, { type: "select", key: "hoy:sig-3" });
    const newAfter = homeRows(home({ today: view([card(1), card(2), card(5)]) }));
    assert.equal(selectedKey(refresh(tail, newAfter), newAfter), "hoy:sig-5");
  });

  it("keeps what was there in place on refresh, adds what is new at the end of its section and keeps the selection", () => {
    const first = home({ today: view([meeting(1), card(2), card(3), card(4)]), followups: [followup(5), followup(6)] });
    const held = holdOrder(null, first);
    assert.deepEqual(held.view, first);
    const start = homeSelection(refresh(initialHomeSelection, homeRows(held.view)), { type: "select", key: "hoy:sig-3" });

    const reordered = home({
      today: view([meeting(1), card(7), card(4), card(3), card(2)]),
      followups: [followup(8), followup(6), followup(5)],
    });
    const next = holdOrder(held.order, reordered);
    assert.deepEqual(callContacts(next.view), ["c2", "c3", "c4", "c7"]);
    assert.deepEqual(section(next.view, "needs_ok").rows.map((row) => row.memoId), ["f5", "f6", "f8"]);
    assert.deepEqual(section(next.view, "needs_ok").shown.map((row) => row.memoId), ["f5", "f6", "f8"]);
    const rows = homeRows(next.view);
    assert.equal(selectedKey(refresh(start, rows), rows), "hoy:sig-3");

    const dropped = holdOrder(next.order, home({ today: view([meeting(1), card(4), card(2)]) }));
    assert.deepEqual(callContacts(dropped.view), ["c2", "c4"]);
  });

  it("snoozes until midnight tomorrow in the given zone, across a clock change", () => {
    assert.equal(snoozeUntil(NOW, TZ), "2026-09-29T22:00:00.000Z");
    assert.equal(snoozeUntil(Date.parse("2026-10-24T12:00:00+02:00"), TZ), "2026-10-24T22:00:00.000Z");
    assert.equal(snoozeUntil(Date.parse("2026-10-25T12:00:00+01:00"), TZ), "2026-10-25T23:00:00.000Z");
    assert.equal(snoozeUntil(Date.parse("2026-09-29T00:30:00+02:00"), TZ), "2026-09-29T22:00:00.000Z");
    assert.equal(snoozeUntil(Date.parse("2026-09-29T23:30:00+02:00"), TZ), "2026-09-29T22:00:00.000Z");
  });

  it("locks selection while on a call", () => {
    const rows = homeRows(day);
    const start = refresh(initialHomeSelection, rows);
    const live = homeSelection(start, { type: "call" });
    assert.equal(live.mode, "calling");
    assert.equal(selectedKey(homeSelection(live, { type: "select", key: "hoy:sig-4" }), rows), "hoy:sig-3");
    assert.equal(selectedKey(homeSelection(live, { type: "next" }), rows), "hoy:sig-3");
    assert.equal(selectedKey(homeSelection(live, { type: "skip" }), rows), "hoy:sig-3");
  });

  it("opens review after a connected call and n moves to the next row", () => {
    const rows = homeRows(day);
    const start = refresh(initialHomeSelection, rows);
    const live = homeSelection(start, { type: "call" });
    const review = homeSelection(live, { type: "call_ended", memoId: "memo-1", screeningOutcome: "connected" });
    assert.equal(review.mode, "review");
    assert.equal(review.memoId, "memo-1");
    const next = homeSelection(review, { type: "reviewed" });
    assert.equal(selectedKey(next, rows), "hoy:sig-4");
  });

  it("advances on voicemail without review", () => {
    const rows = homeRows(home({ today: view([card(1), card(2)]) }));
    const start = refresh(initialHomeSelection, rows);
    const live = homeSelection(start, { type: "call" });
    const next = homeSelection(live, { type: "call_ended", memoId: "memo-vm", screeningOutcome: "voicemail" });
    assert.equal(next.mode, "queue");
    assert.equal(selectedKey(next, rows), "hoy:sig-2");
    assert.equal(next.lastOutcome, "no_answer");
  });

  it("locks onto the row of the contact the dialer is calling, even from another selection", () => {
    const rows = homeRows(day);
    const start = refresh(initialHomeSelection, rows);
    const live = homeSelection(start, { type: "call", key: "hoy:sig-4" });
    assert.equal(live.mode, "calling");
    assert.equal(selectedKey(live, rows), "hoy:sig-4");
    assert.equal(homeSelection(start, { type: "call", key: "hoy:missing" }), start);
    const idle = homeSelection(start, { type: "exit" });
    assert.equal(selectedKey(homeSelection(idle, { type: "call", key: "hoy:sig-3" }), rows), "hoy:sig-3");
    assert.equal(homeSelection(live, { type: "call", key: "hoy:sig-3" }), live);
  });

  it("stays on the row with a failed outcome when the call never connected", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const next = homeSelection(live, { type: "call_ended", answered: false, callSid: "CA1" });
    assert.equal(next.mode, "queue");
    assert.equal(selectedKey(next, rows), "hoy:sig-3");
    assert.equal(next.lastOutcome, "failed");
    assert.equal(homeSelection(next, { type: "call" }).lastOutcome, undefined);
  });

  it("opens review for an answered call before the memo exists, and n still moves on", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const review = homeSelection(live, { type: "call_ended", answered: true, callSid: "CA2" });
    assert.equal(review.mode, "review");
    assert.equal(review.memoId, undefined);
    assert.equal(review.callSid, "CA2");
    assert.equal(selectedKey(homeSelection(review, { type: "reviewed" }), rows), "hoy:sig-4");
  });

  it("advances and notes the called row when the processed call turns out to be voicemail", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const review = homeSelection(live, { type: "call_ended", answered: true, callSid: "CA3" });
    const next = homeSelection(review, { type: "call_resolved", outcome: "no_answer", callSid: "CA3" });
    assert.equal(next.mode, "queue");
    assert.equal(selectedKey(next, rows), "hoy:sig-4");
    assert.deepEqual(next.lastCall, { key: "hoy:sig-3", outcome: "no_answer" });
    const failed = homeSelection(review, { type: "call_resolved", outcome: "failed", callSid: "CA3" });
    assert.equal(selectedKey(failed, rows), "hoy:sig-3");
    assert.equal(failed.lastOutcome, "failed");
  });

  it("ignores a late resolution once the rep moved on or for another call", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const review = homeSelection(live, { type: "call_ended", answered: true, callSid: "CA4" });
    assert.equal(homeSelection(review, { type: "call_resolved", outcome: "no_answer", callSid: "CA9" }), review);
    const moved = homeSelection(review, { type: "reviewed" });
    assert.equal(homeSelection(moved, { type: "call_resolved", outcome: "no_answer", callSid: "CA4" }), moved);
  });

  it("moves to the adjacent row with j/k from review", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const review = homeSelection(live, { type: "call_ended", memoId: "memo-1" });
    assert.equal(selectedKey(homeSelection(review, { type: "next" }), rows), "hoy:sig-4");
    assert.equal(selectedKey(homeSelection(review, { type: "prev" }), rows), "review:r6");
  });

  it("keeps the call on its contact when a refresh drops that row", () => {
    const rows = homeRows(day);
    const live = homeSelection(refresh(initialHomeSelection, rows), { type: "call" });
    const without = rows.filter((row) => row.key !== "hoy:sig-3");
    const after = refresh(live, without);
    assert.equal(after.mode, "calling");
    assert.equal(after.items[after.index], "hoy:sig-3");
  });
});
