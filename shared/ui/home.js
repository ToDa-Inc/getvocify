// The rep's home in one pure pass: six reads in, the sections to paint out.
// A read still loading arrives as undefined; one that failed arrives as null and only its own
// section goes missing. No state is claimed until the reads that decide it have answered.
// A local action result never beats a newer /today version: nothing is invented.

export const HOME_CAP = 7;
export const NEEDS_OK_VISIBLE = 3;
export const REVIEW_LIMIT = 5;
export const CONFIRM_GROUP_AT = 3;
export const FOLLOWUP_POLL_MS = 5000;
export const FOLLOWUP_POLL_FOR_MS = 120_000;

const MEETING = "meeting_today";
const CONFIRM = "confirm_pending";
const TASK = "manual_task";
const PRIORITY_TYPES = { pain_agree_next_step: "pain_confirmed", no_calls_logged: "uncalled" };
const DONE_KINDS = new Set(["call", "followup", "signal", "confirmation"]);
const MANAGERS = new Set(["owner", "admin"]);

export function composeHome(input) {
  const { today, now } = input;
  const canManage = MANAGERS.has(input.role);
  if (today === undefined) {
    return { state: "loading", canManage, incompleteAt: null, pulse: null, folded: null, sections: [] };
  }

  const items = today ? mergeActed(today.items || [], input.acted || [], now) : [];
  const meetings = items.filter((item) => item.type === MEETING && !item.memo_id);
  const confirms = items.filter((item) => item.type === CONFIRM);
  const todayCalls = items.filter((item) => ![MEETING, CONFIRM, TASK].includes(item.type));
  const calls = [
    ...todayCalls.map((item) => ({ source: "today", item })),
    ...priorityCalls(input.priorities, items),
  ];

  let budget = HOME_CAP;
  const shownMeetings = meetings.slice(0, budget);
  budget -= shownMeetings.length;
  const confirmRows = confirmationRows(confirms, budget);
  budget -= confirmRows.cost;
  const shownCalls = calls.slice(0, budget);
  const tasksShown = (today?.items || []).some((item) => item.type === TASK);
  const foldedCount = (meetings.length - shownMeetings.length)
    + confirmRows.folded
    + (calls.length - shownCalls.length)
    + (tasksShown ? 0 : today?.folded_count || 0);
  const lastHoy = shownCalls.length ? "calls" : confirmRows.rows.length ? "needs_ok" : shownMeetings.length ? "meetings" : null;

  const needsOk = [...confirmRows.rows, ...followupRows(input.followups), ...reviewRows(input.reviews)];
  const upcoming = (input.upcoming || []).map((row) => ({
    ...row,
    inCrm: Boolean(row.crm_task_id),
    when: dayLabel(row.due_at, now, input),
  }));
  const done = doneRows(input.done, input);

  const sections = [];
  if (shownMeetings.length) {
    sections.push({ id: "meetings", items: shownMeetings.map((item) => meetingEntry(item, input)) });
  }
  if (needsOk.length) {
    sections.push({
      id: "needs_ok",
      rows: needsOk,
      shown: needsOk.slice(0, NEEDS_OK_VISIBLE),
      more: Math.max(0, needsOk.length - NEEDS_OK_VISIBLE),
    });
  }
  if (shownCalls.length) sections.push({ id: "calls", items: shownCalls });
  if (upcoming.length) sections.push({ id: "upcoming", rows: upcoming });
  if (done.length) sections.push({ id: "done", rows: done, count: done.length });

  const deciding = [input.priorities, input.followups, input.reviews];
  const settled = deciding.every((read) => read !== undefined) && input.connected !== undefined;
  const sideFailed = deciding.some((read) => read === null);
  const incomplete = Boolean(today) && (input.todayStale || sideFailed || !sourcesComplete(today.coverage));
  const pending = shownMeetings.length + needsOk.length + shownCalls.length > 0;
  const todayCards = meetings.length + confirms.length + todayCalls.length > 0;

  let state = "day";
  if (today === null) state = "error";
  else if (input.connected === false && !todayCards) state = "connect";
  else if (!pending && !incomplete && settled) {
    state = input.priorities?.title === "title_no_assigned" ? "no_assigned" : "clear";
  }

  return {
    state,
    canManage,
    incompleteAt: incomplete ? clock(today.generated_at, input) : null,
    pulse: pulse(done, input),
    folded: foldedCount > 0 ? { count: foldedCount, after: lastHoy } : null,
    sections,
  };
}

/** Poll drafts being written every few seconds, but give up after a while so a stuck one does not poll forever. */
export function followupPoll(rows, since, now) {
  if (!(rows || []).some((row) => row.status === "generating")) return { interval: false, since: null };
  const start = since ?? now;
  return { interval: now - start < FOLLOWUP_POLL_FOR_MS ? FOLLOWUP_POLL_MS : false, since: start };
}

/** A 409 on resolve or undo carries the real row: forget the local result and read /today again. */
export function afterActionError(error) {
  if (!error || error.status !== 409) return null;
  const row = error.data?.detail;
  const id = row && typeof row === "object" && row.id ? String(row.id) : null;
  return { forget: id, refetch: true };
}

function mergeActed(serverItems, acted, now) {
  const byId = new Map(acted.filter((item) => item.id).map((item) => [item.id, item]));
  const undoOpen = (item) => item.undo_deadline != null && Date.parse(item.undo_deadline) >= now;
  const seen = new Set();
  const out = [];
  for (const item of serverItems) {
    if (item.id) seen.add(item.id);
    const local = item.id ? byId.get(item.id) : null;
    if (!local || (local.version ?? -1) <= (item.version ?? -1)) {
      out.push(item);
    } else if (local.status === "pending" || undoOpen(local)) {
      out.push(local);
    }
  }
  for (const local of acted) {
    if (local.id && !seen.has(local.id) && local.status !== "pending" && undoOpen(local)) out.push(local);
  }
  return out;
}

function priorityCalls(view, todayItems) {
  const known = new Set(todayItems.filter((item) => item.type !== TASK && item.contact_id).map((item) => item.contact_id));
  const out = [];
  for (const candidate of view?.items || []) {
    const type = PRIORITY_TYPES[candidate.reason];
    if (!type || known.has(candidate.contact_id)) continue;
    known.add(candidate.contact_id);
    out.push({
      source: "priority",
      item: {
        type,
        id: null,
        dedupe_key: `priority:${candidate.id}`,
        contact_id: candidate.contact_id,
        contact_name: candidate.contact_name ?? null,
        company_name: null,
        reason: candidate.reason,
        detail: null,
        origins: ["priority"],
        supporting: [],
      },
    });
  }
  return out;
}

function confirmationRows(confirms, budget) {
  if (!confirms.length) return { rows: [], cost: 0, folded: 0 };
  if (confirms.length >= CONFIRM_GROUP_AT) {
    if (budget < 1) return { rows: [], cost: 0, folded: confirms.length };
    return { rows: [{ kind: "confirm_group", count: confirms.length, items: confirms, action: "expand" }], cost: 1, folded: 0 };
  }
  const shown = confirms.slice(0, Math.max(0, budget));
  return {
    rows: shown.map((item) => ({ kind: "confirm", item, action: "confirm" })),
    cost: shown.length,
    folded: confirms.length - shown.length,
  };
}

function followupRows(rows) {
  return (rows || []).map((row) => ({
    kind: "followup",
    memoId: row.memo_id,
    name: row.contact_name ?? null,
    subject: row.status === "ready" ? row.subject ?? null : null,
    status: row.status,
    action: row.status === "generating" ? null : "open",
  }));
}

function reviewRows(memos) {
  return (memos || []).map((memo) => ({
    kind: "review",
    memoId: memo.id,
    name: memo.extraction?.contactName ?? null,
    action: "review",
  }));
}

function doneRows(rows, fmt) {
  const known = (rows || []).filter((row) => DONE_KINDS.has(row.kind));
  const calls = known.filter((row) => row.kind === "call");
  return known
    .filter((row) => !(row.kind === "signal" && calls.some((call) => sameContact(row, call))))
    .map((row) => ({
      kind: row.kind,
      name: row.contact_name ?? null,
      contactId: row.contact_id ?? null,
      at: row.at,
      memoId: row.memo_id ?? null,
      time: clock(row.at, fmt),
    }));
}

function pulse(done, input) {
  const calls = done.filter((row) => row.kind === "call");
  if (!calls.length) return null;
  const reviews = input.reviews;
  const pendingIds = new Set((reviews || []).map((memo) => memo.id));
  const saved = Boolean(input.connected && input.crm)
    && Array.isArray(reviews)
    && reviews.length < REVIEW_LIMIT
    && calls.every((row) => row.memoId && !pendingIds.has(row.memoId));
  return { calls: calls.length, savedTo: saved ? input.crm : null };
}

function meetingEntry(item, fmt) {
  const timed = item.precision !== "date" && Boolean(item.due_at);
  const at = timed ? Date.parse(item.due_at) : NaN;
  return {
    item,
    time: timed ? clock(item.due_at, fmt) : null,
    past: timed && !Number.isNaN(at) && at < fmt.now,
  };
}

function sourcesComplete(coverage) {
  const values = Object.values(coverage || {});
  return values.length > 0 && values.every((value) => value === "complete");
}

function sameContact(a, b) {
  if (a.contact_id && b.contact_id) return a.contact_id === b.contact_id;
  const name = nameKey(a.contact_name);
  return Boolean(name) && name === nameKey(b.contact_name);
}

function nameKey(name) {
  return String(name || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function clock(iso, { locale, timeZone }) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", timeZone }).format(date);
}

function calendarDay(ms, timeZone) {
  const [year, month, day] = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" })
    .format(new Date(ms))
    .split("-")
    .map(Number);
  return Date.UTC(year, month - 1, day);
}

function capitalize(text) {
  return text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text;
}

function dayLabel(iso, now, { locale, timeZone }) {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  const offset = Math.round((calendarDay(at, timeZone) - calendarDay(now, timeZone)) / 86_400_000);
  if (offset === 1) {
    return capitalize(new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(1, "day"));
  }
  const parts = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", timeZone })
    .formatToParts(new Date(at))
    .filter((part) => part.type !== "literal")
    .map((part) => part.value);
  return capitalize(parts.join(" "));
}
