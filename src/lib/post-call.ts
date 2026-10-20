/**
 * The Mac notch island's card after a recorded call. Every row comes from something the
 * backend produced for this call and that still needs the rep; nothing is invented, and
 * a row that doesn't apply is simply absent.
 *
 * No `@/` imports: this file runs under node --test.
 */
import { canEditOrRemoveProposedField, proposedFieldKey, type ProposedUpdate } from "./extraction-omit.ts";
import { CONFIDENCE } from "../shared/lib/constants.ts";

/** The CRM record a change lands on; the island groups the changes by it. */
export type PostCallObject = "contact" | "company" | "deal" | "other";

export type PostCallOption = { value: string; label: string };

/** One proposed CRM change, as the island lists it. */
export type PostCallChange = {
  /** `object_type:field_name`, the key the review screen omits fields by. */
  key: string;
  label: string;
  object: PostCallObject;
  /** What the CRM has now and what it becomes, as the rep reads them (option labels). */
  from: string | null;
  to: string;
  /** What gets written: the option value(s), ";"-joined for a checkbox list. */
  value: string;
  /** The values the rep can pick from in place; empty when the value is free text. */
  options: PostCallOption[];
  /** A checkbox list: several options at once. */
  multiple: boolean;
  /** Free text the rep can type over in the island (see `typedValue`); false for a value with options. */
  editable: boolean;
  /** Extraction confidence under CONFIDENCE.MEDIUM ("needs review"): ticked like the rest, marked as less sure. */
  check: boolean;
  /** A task's day and hour, e.g. "Tue 20 Oct, 09:00", in the rep's own zone; null for anything else. */
  when: string | null;
  /** The call gave the task no day: `when` is the default it will be written with. */
  whenSuggested: boolean;
  /** A task's due moment (ISO, with offset), which the island's day and hour picker starts from. Absent on anything else. */
  dueAt?: string;
  /** Nothing was proposed (the lead status the call left alone): written only once the rep picks a value. */
  pending?: boolean;
};

export type PostCallCrmStage =
  /** The memo is being extracted. */
  | "writing"
  /** Changes ready: approve here (when safe) or review in Vocify. */
  | "ready"
  /** Approved: the write waits out the undo window, then runs. */
  | "applying"
  | "done"
  /** Needs the review screen (a choice to make, or something went wrong). */
  | "review"
  /** An internal conversation: nothing goes to the CRM. */
  | "internal";

export type PostCallEmail = {
  /** writing: the draft is on its way. ready: drafted, not sent. skipped/sent: settled. */
  state: "writing" | "ready" | "skipped" | "sent";
  /** Who it's for, as extracted. */
  to: string | null;
  subject: string | null;
  /** The draft's opening, to read it without opening it. */
  preview: string | null;
};

export type PostCallMeeting = {
  proposalId: string;
  /** "agreed" with a time: one click adds it to the CRM. "check": needs a correction in review. */
  state: "pending" | "check" | "added";
  /** e.g. "Tue 7 Oct, 10:00", in the proposal's time zone. */
  when: string | null;
};

/** What the call was scored as (its type), and the other published types it can be changed to. */
export type PostCallType = { key: string; label: string; options: { key: string; label: string }[] };

type MemoPlaybookView = {
  sales_motion_key?: string | null;
  can_change?: boolean;
  options?: { key: string; label: string | null }[];
};

/** The type row, or null when the memo has none. Options only when the viewer can change it. */
export function callTypeFrom(
  view: MemoPlaybookView | null | undefined,
  name: (key: string, label?: string | null) => string,
): PostCallType | null {
  const key = view?.sales_motion_key;
  if (!key) return null;
  const all = (view?.options ?? []).map((option) => ({ key: option.key, label: name(option.key, option.label) }));
  return {
    key,
    label: all.find((option) => option.key === key)?.label ?? name(key),
    options: view?.can_change ? all.filter((option) => option.key !== key) : [],
  };
}

/** The type row after choosing `key`: the old one goes back among the options, in `order`. */
export function retypedTo(type: PostCallType, key: string, order: string[]): PostCallType | null {
  const next = type.options.find((option) => option.key === key);
  if (!next) return null;
  const options = [...type.options.filter((option) => option.key !== key), { key: type.key, label: type.label }];
  options.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return { key, label: next.label, options };
}

/** The type key of a conversation without a customer. */
export const INTERNAL_TYPE = "internal";

/** The CRM part of the card for a call of this type: an internal one has nothing for the CRM. */
export function crmForType(
  typeKey: string | null | undefined,
  crm: Pick<PostCall, "stage" | "changes" | "canApprove" | "note">,
): Pick<PostCall, "stage" | "changes" | "canApprove" | "note"> {
  return typeKey === INTERNAL_TYPE ? { stage: "internal", changes: [], canApprove: false, note: undefined } : crm;
}

export type PostCall = {
  memoId: string;
  contactName: string | null;
  stage: PostCallCrmStage;
  changes: PostCallChange[];
  /** One click is safe: the memo knows its contact and nothing needs a choice. */
  canApprove: boolean;
  /** How many changes were written, once done. */
  applied?: number;
  /** While applying: epoch ms until which Undo still stops the write. */
  undoUntil?: number;
  note?: string;
  email: PostCallEmail | null;
  meeting: PostCallMeeting | null;
  /** The memo has a call note to read. */
  notes: boolean;
  /** The call note as plain text, one line per line of the note. */
  summary?: string | null;
  /** Nobody answered (a voicemail): the card offers only the lead status and tasks, and no note is written. */
  noAnswer?: boolean;
  /** The connected CRM's name ("HubSpot", "Pipedrive"...); null when none is known. */
  crm?: string | null;
  type?: PostCallType | null;
  /** The updated record in the CRM, once written. */
  crmUrl?: string | null;
};

type Update = ProposedUpdate & { extraction_confidence?: number | null };

function text(value: unknown): string {
  return value == null ? "" : String(value).replace(/\s+/g, " ").trim();
}

const OBJECTS: Record<string, PostCallObject> = { contacts: "contact", companies: "company", deals: "deal" };

function optionsOf(update: Update): PostCallOption[] {
  if (!canEditOrRemoveProposedField(update)) return [];
  const options: PostCallOption[] = [];
  for (const raw of update.options ?? []) {
    const option = raw as { value?: unknown; label?: unknown } | null;
    const value = text(option?.value);
    if (value) options.push({ value, label: text(option?.label) || value });
  }
  return options;
}

/** CRM field types whose value can be typed: text, and numbers (checked as numbers). Dates and the like are not. */
const TYPABLE = new Set(["", "string", "text", "textarea", "phone_number", "phonenumber", "number"]);

/** A free-text field the rep may type a new value for in the island: one the review screen may edit, with no options. */
function typable(update: Update): boolean {
  return canEditOrRemoveProposedField(update) && optionsOf(update).length === 0 && TYPABLE.has(text(update.field_type).toLowerCase());
}

/** What the rep typed, as the field takes it, or null when it can't be written (blank, or not a number for a number field). */
function typedValue(update: Update, typed: string): string | null {
  const value = typed.replace(/\s+/g, " ").trim();
  if (!value) return null;
  if (text(update.field_type).toLowerCase() === "number") return /^-?\d+(\.\d+)?$/.test(value) ? value : null;
  return value;
}

/** A value as the rep reads it: option labels instead of the CRM's internal values. */
export function shownValue(value: string, options: PostCallOption[], multiple: boolean): string {
  if (!options.length) return value;
  const label = (part: string) => options.find((option) => option.value === part)?.label ?? part;
  return multiple ? value.split(";").map((part) => part.trim()).filter(Boolean).map(label).join(", ") : label(value);
}

/** The changes worth naming: a new value that differs from what the CRM has. */
export function changesFrom(proposed: Update[] | null | undefined): PostCallChange[] {
  const changes: PostCallChange[] = [];
  for (const update of proposed ?? []) {
    const key = proposedFieldKey(update);
    const to = text(update.new_value);
    const from = text(update.current_value);
    if (key && !to && update.field_name === LEAD_STATUS_FIELD) {
      const options = optionsOf(update);
      if (options.length) {
        changes.push({ key, label: text(update.field_label) || "Lead status", object: "contact", from: null, to: "Choose", value: "", options, multiple: false, editable: false, check: false, pending: true, when: null, whenSuggested: false });
      }
      continue;
    }
    if (!key || !to || to === from) continue;
    const confidence = typeof update.extraction_confidence === "number" ? update.extraction_confidence : null;
    const dueAt = update.object_type === "task" ? text(update.due_at) : "";
    const options = optionsOf(update);
    const multiple = options.length > 0 && Boolean(update.multiple);
    changes.push({
      key,
      label: text(update.field_label) || text(update.field_name),
      object: OBJECTS[update.object_type || "deals"] ?? "other",
      from: from ? shownValue(from, options, multiple) : null,
      to: shownValue(to, options, multiple),
      value: to,
      options,
      multiple,
      editable: typable(update),
      check: confidence !== null && confidence < CONFIDENCE.MEDIUM,
      when: dueAt ? meetingWhen(dueAt, null) : null,
      whenSuggested: Boolean(dueAt && update.due_date_inferred),
      ...(dueAt ? { dueAt } : {}),
    });
  }
  return changes;
}

/** The CRM's contact field for the lead status, as its schema lists it. */
export const LEAD_STATUS_FIELD = "hs_lead_status";

type SchemaProperty = { name: string; label?: string; options?: { label: string; value: string }[] };

/**
 * The lead status offered when the call proposed none, so every call can end with it: the field with its
 * options, nothing chosen. Null when the CRM has no such field or no options, so nothing is invented.
 */
export function leadStatusUpdate(properties: SchemaProperty[] | null | undefined): Update | null {
  const property = (properties ?? []).find((candidate) => candidate.name === LEAD_STATUS_FIELD);
  const options = (property?.options ?? []).filter((option) => text(option.value));
  if (!property || options.length === 0) return null;
  return {
    field_name: LEAD_STATUS_FIELD,
    field_label: text(property.label) || "Lead status",
    field_type: "enumeration",
    object_type: "contacts",
    new_value: "",
    current_value: null,
    options,
    multiple: false,
  };
}

/** The proposed updates plus the lead status to choose, unless the call already proposed one. */
export function withLeadStatus(proposed: Update[] | null | undefined, offer: Update | null): Update[] {
  const list = proposed ?? [];
  if (!offer || list.some((update) => proposedFieldKey(update) === proposedFieldKey(offer))) return list;
  return [...list, offer];
}

/**
 * The proposed updates as the rep left them in the island: a value picked from the options
 * replaces the extracted one, and so does text typed over a free-text value (see `typable`).
 * A pick outside the field's options, or text a field can't take, is ignored.
 */
export function withEdits(proposed: Update[], edits: Record<string, unknown> | null | undefined): Update[] {
  if (!edits) return proposed;
  return proposed.map((update) => {
    const key = proposedFieldKey(update);
    const edit = key ? edits[key] : undefined;
    if (typeof edit !== "string") return update;
    if (typable(update)) {
      const typed = typedValue(update, edit);
      return typed === null ? update : { ...update, new_value: typed };
    }
    const allowed = new Set(optionsOf(update).map((option) => option.value));
    const parts = update.multiple ? edit.split(";").filter(Boolean) : [edit];
    if (!parts.length || !parts.every((part) => allowed.has(part))) return update;
    return { ...update, new_value: parts.join(";") };
  });
}

/** A note line as the rep reads it: no heading or bullet marks, no bold. */
function plainLine(line: string): string {
  return line.replace(/^\s*(?:#+\s*|[-*•]\s+|\d+[.)]\s+)/, "").replace(/\*\*|__|`/g, "").trim();
}

/** The note's first lines as plain text, for the island's Notes tab. */
export function summaryLines(markdown: string | null | undefined, max = Infinity): string | null {
  const lines = String(markdown ?? "")
    .split("\n")
    .map(plainLine)
    .filter(Boolean)
    .slice(0, max);
  return lines.length ? lines.join("\n") : null;
}

/** A task the rep added in the island's card: its title, the day it is due (YYYY-MM-DD) and, when chosen, the hour (HH:MM). */
export type NewTask = { title: string; due: string; time?: string };

/** The day and hour the rep chose for a task (an added one, or a proposed one they moved). */
export type TaskDue = { due: string; time?: string };

const DUE_DAY = /^\d{4}-\d{2}-\d{2}$/;
const DUE_TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

function dueFrom(row: Record<string, unknown> | null): TaskDue | null {
  const due = typeof row?.due === "string" ? row.due : "";
  if (!DUE_DAY.test(due) || Number.isNaN(Date.parse(`${due}T00:00:00Z`))) return null;
  const time = typeof row?.time === "string" && DUE_TIME.test(row.time) ? row.time : undefined;
  return time ? { due, time } : { due };
}

/** The tasks the island sent, as far as they can be written: a title and a real YYYY-MM-DD day. Anything else is dropped. */
export function newTasksFrom(raw: unknown): NewTask[] {
  if (!Array.isArray(raw)) return [];
  const tasks: NewTask[] = [];
  for (const item of raw.slice(0, 20)) {
    const row = item && typeof item === "object" ? (item as Record<string, unknown>) : null;
    const title = typeof row?.title === "string" ? row.title.replace(/\s+/g, " ").trim().slice(0, 200) : "";
    const due = dueFrom(row);
    if (title && due) tasks.push({ title, ...due });
  }
  return tasks;
}

/** What the rep changed on one of the call's proposed tasks: its text, and/or the day and hour it is due. */
export type TaskEdit = { title?: string; due?: string; time?: string };

/** The changes the rep made to the call's proposed tasks in the island, by the task's change key. Only real values are kept. */
export function taskEditsFrom(raw: unknown): Record<string, TaskEdit> {
  const edits: Record<string, TaskEdit> = {};
  if (!raw || typeof raw !== "object") return edits;
  for (const [key, value] of Object.entries(raw as Record<string, unknown>).slice(0, 40)) {
    const row = value && typeof value === "object" ? (value as Record<string, unknown>) : null;
    const title = typeof row?.title === "string" ? row.title.replace(/\s+/g, " ").trim().slice(0, 200) : "";
    const due = dueFrom(row);
    if (title || due) edits[key] = { ...(title ? { title } : {}), ...(due ?? {}) };
  }
  return edits;
}

/** A day and hour the way a task's schedule hint reads them: the backend takes "YYYY-MM-DD a las HH:MM". */
export function dueHint({ due, time }: TaskDue): string {
  return time ? `${due} a las ${time}` : due;
}

function isTaskUpdate(update: Update): boolean {
  return update.object_type === "task" || String(update.field_name || "").startsWith("next_step_task_");
}

/**
 * The tasks to write: the call's proposed ones the rep kept (a task they moved carries its new day and hour, marked in
 * `reviewedTaskDates` so the backend writes it as chosen; one they re-worded is written from its new text), then the ones they added. A call that proposed no task rows keeps
 * the steps the extraction had.
 */
export function tasksForApprove(
  extraction: { nextSteps?: string[] | null; raw_extraction?: Record<string, unknown> } | null | undefined,
  proposed: Update[] | null | undefined,
  omit: string[],
  edits: Record<string, TaskEdit>,
  added: NewTask[],
): { nextSteps: string[]; nextStepSchedules: string[]; reviewedTaskDates: string[] } {
  const rows = (proposed ?? []).filter(isTaskUpdate);
  if (rows.length === 0) {
    const steps = withAddedTasks(extraction, added);
    const schedules = steps.nextStepSchedules ?? [];
    return { nextSteps: steps.nextSteps, nextStepSchedules: schedules, reviewedTaskDates: schedules.map(() => "") };
  }
  const index = (update: Update) => parseInt(String(update.field_name).replace("next_step_task_", ""), 10) || 0;
  const kept = rows
    .filter((update) => !omit.includes(proposedFieldKey(update) ?? ""))
    .sort((a, b) => index(a) - index(b))
    .map((update) => ({ step: text(update.new_value), update }))
    .filter((row) => row.step);
  const editOf = (update: Update) => {
    const key = proposedFieldKey(update);
    return key ? edits[key] : undefined;
  };
  // Re-worded, a task is no longer the commitment's text: it keeps the day and hour the call gave it.
  const given = (update: Update) => {
    const at = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(text(update.due_at));
    return at ? `${at[1]} a las ${at[2]}` : text(update.due_date);
  };
  const steps = kept.map((row) => editOf(row.update)?.title ?? row.step);
  const schedules = kept.map((row) => {
    const edit = editOf(row.update);
    if (edit?.due) return dueHint({ due: edit.due, time: edit.time });
    return edit?.title ? given(row.update) : text(row.update.due_date);
  });
  const reviewed = kept.map((row) => {
    const edit = editOf(row.update);
    return edit?.due ? dueHint({ due: edit.due, time: edit.time }) : "";
  });
  return {
    nextSteps: [...steps, ...added.map((task) => task.title)],
    nextStepSchedules: [...schedules, ...added.map((task) => dueHint(task))],
    reviewedTaskDates: [...reviewed, ...added.map(() => "")],
  };
}

/**
 * The call's next steps with the rep's tasks after them, and the day of each step in the same order (the backend writes
 * a next step as a CRM task and reads its day from there). Nothing added leaves the extraction's steps and days as they are.
 */
export function withAddedTasks(
  extraction: { nextSteps?: string[] | null; raw_extraction?: Record<string, unknown> } | null | undefined,
  added: NewTask[],
): { nextSteps: string[]; nextStepSchedules?: string[] } {
  const steps = extraction?.nextSteps ?? [];
  if (added.length === 0) return { nextSteps: steps };
  const raw = extraction?.raw_extraction ?? {};
  const known = Array.isArray(raw.nextStepSchedules) ? raw.nextStepSchedules : Array.isArray(raw.next_step_schedules) ? raw.next_step_schedules : [];
  const days = steps.map((_, i) => (typeof known[i] === "string" ? (known[i] as string) : ""));
  return { nextSteps: [...steps, ...added.map((task) => task.title)], nextStepSchedules: [...days, ...added.map((task) => dueHint(task))] };
}

/**
 * The note the rep edited in the island, back as the note's markdown: a line they left as it
 * was keeps its heading, bullet and bold; a line they wrote or changed is plain text. Lines
 * are blank-line separated, so the CRM note keeps one line per line either way.
 */
export function noteMarkdown(text: string, original: string | null | undefined): string {
  const kept = new Map<string, string>();
  for (const line of String(original ?? "").split("\n")) {
    const plain = plainLine(line);
    if (plain && !kept.has(plain)) kept.set(plain, line.trim());
  }
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => kept.get(line) ?? line)
    .join("\n\n");
}

/** The changes ticked by default: all of them. The rep unticks what should not be written. */
export function defaultKept(changes: PostCallChange[]): string[] {
  return changes.map((change) => change.key);
}

type FollowupView = { status?: string | null; recipientName?: string | null; subject?: string | null; body?: string | null };

/** How much of the draft the island shows: a few lines, the rest is in Vocify. */
const EMAIL_PREVIEW_CHARS = 280;

export function emailFrom(view: FollowupView | null | undefined): PostCallEmail | null {
  const status = view?.status;
  if (status === "generating") return { state: "writing", to: text(view?.recipientName) || null, subject: null, preview: null };
  if (status !== "ready" && status !== "skipped" && status !== "sent") return null;
  const body = text(view?.body);
  return {
    state: status,
    to: text(view?.recipientName) || null,
    subject: text(view?.subject) || null,
    preview: body ? (body.length > EMAIL_PREVIEW_CHARS ? `${body.slice(0, EMAIL_PREVIEW_CHARS).trimEnd()}…` : body) : null,
  };
}

type MeetingProposal = {
  proposal_id?: unknown;
  agreement?: unknown;
  starts_at?: unknown;
  timezone?: unknown;
  decision?: unknown;
  needs_review?: unknown;
};

export function meetingWhen(startsAt: string, timeZone: string | null, locale = "en-GB"): string | null {
  const date = new Date(startsAt);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(locale, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timeZone || undefined,
    }).format(date);
  } catch {
    return null;
  }
}

/** Only a meeting the call actually agreed. Accepting creates a CRM meeting task, not an invite. */
export function meetingFrom(proposal: MeetingProposal | null | undefined, locale?: string): PostCallMeeting | null {
  const proposalId = text(proposal?.proposal_id);
  if (!proposal || !proposalId || proposal.agreement !== "agreed") return null;
  const decision = text(proposal.decision) || "pending";
  const startsAt = text(proposal.starts_at);
  const when = startsAt ? meetingWhen(startsAt, text(proposal.timezone) || null, locale) : null;
  if (decision === "accepted" || decision === "corrected") return { proposalId, state: "added", when };
  if (decision !== "pending") return null;
  return { proposalId, state: proposal.needs_review || !when ? "check" : "pending", when };
}

/** The CRM part for a memo's status; `proposed` is the review preview, fetched once ready. */
export function crmFor(
  memo: { status: string; hubspotContactId?: string | null },
  proposed?: Update[] | null,
): Pick<PostCall, "stage" | "changes" | "canApprove" | "note"> {
  switch (memo.status) {
    case "approved":
      return { stage: "done", changes: [], canApprove: false };
    case "pending_review": {
      const changes = changesFrom(proposed);
      if (!changes.length) return { stage: "review", changes, canApprove: false, note: "Nothing to change in the CRM" };
      return { stage: "ready", changes, canApprove: Boolean(memo.hubspotContactId) };
    }
    case "failed":
    case "rejected":
      return { stage: "review", changes: [], canApprove: false, note: "Needs a look" };
    default:
      return { stage: "writing", changes: [], canApprove: false };
  }
}

/** What still needs the rep: the count on the closed island, and whether the card can go. */
export function pendingItems(postCall: PostCall | null): number {
  if (!postCall) return 0;
  let count = 0;
  if (postCall.stage === "ready" || postCall.stage === "review") count += 1;
  if (postCall.email?.state === "ready") count += 1;
  if (postCall.meeting && postCall.meeting.state !== "added") count += 1;
  return count;
}

/** How long Approve can still be undone before the write runs. */
export const UNDO_MS = 5000;

/** Waits between status checks: quick while extraction usually finishes (a few seconds), then gentler. */
export function pollDelayMs(attempt: number): number {
  if (attempt < 8) return 700;
  return attempt < 16 ? 1500 : 4000;
}

/** Long enough for a slow extraction or email draft; after that the memo is left to Vocify. */
export const POST_CALL_GIVE_UP_MS = 4 * 60 * 1000;
