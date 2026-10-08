/**
 * Calling the CRM contact on screen from the desktop island: what the island
 * shows (`onScreen`, `dial` shell state) and the commands it sends back.
 * Contract: docs/superpowers/specs/2026-10-06-desktop-calling-design.md.
 * No `@/` imports: this file runs under node --test.
 */
import { isCallEnded, isCallUp, type CallEngineState, type DialTarget } from "./call-engine-state.ts";
import type { CallPreview } from "./call-contact.ts";

/** CRMs the island can call, with the name it shows. HubSpot only for now. */
const CALLABLE_CRMS: Record<string, string> = { hubspot: "HubSpot" };

export type OnScreenState = "callable" | "no_phone" | "needs_contact" | "no_caller_id";

export type OnScreen = {
  provider: string;
  crmLabel: string;
  name: string | null;
  /** E.164; the island groups it for display. */
  phone: string | null;
  /** The verified number the call goes out from. */
  callerId: string | null;
  state: OnScreenState;
  /** What happened with this contact lately (GET /contacts/{id}/recent-activity), while it loads or once it has lines. */
  brief?: IslandBrief;
};

export type IslandBrief = { state: "loading" } | { state: "ready"; lines: IslandBriefLine[]; company: IslandCompanyBrief | null };

/** What a brief line is about, from the newest interaction it cites (the island shows its icon). */
export type IslandBriefKind = "call" | "email" | "note" | "meeting" | "task" | "vocify_conversation" | "company";

/** A brief line, with the kind and date of the newest interaction it cites; null when the backend did not say. A
 * company line also says who at the company it was with (null when filed on the company alone). */
export type IslandBriefLine = { text: string; type: IslandBriefKind | null; at: string | null; who?: string | null };

/** What was already said with other people at the contact's company: who and when last (from what was read), how
 * many people, and the summary's lines about it. */
export type IslandCompanyBrief = {
  name: string | null;
  latest: { type: IslandBriefKind | null; at: string | null; who: string | null } | null;
  people: number;
  lines: IslandBriefLine[];
};

/** The brief a call keeps while it is up. */
export type IslandCallBrief = { lines: IslandBriefLine[]; company: IslandCompanyBrief | null };

const BRIEF_KINDS = new Set<string>(["call", "email", "note", "meeting", "task", "vocify_conversation", "company"]);

/** The summary's lines for the island. */
const ISLAND_BRIEF_LINES = 3;
const ISLAND_COMPANY_LINES = 2;

type Person = { name?: string | null; title?: string | null } | null | undefined;
type SummaryLine = { text?: string; type?: string | null; occurred_at?: string | null; with?: Person };
type Activity = {
  company?: { name?: string | null } | null;
  company_interactions?: { type?: string | null; occurred_at?: string | null; with?: Person }[] | null;
  summary?: { lines?: SummaryLine[]; company_lines?: SummaryLine[] } | null;
};

const kindOf = (type: string | null | undefined): IslandBriefKind | null => (type && BRIEF_KINDS.has(type) ? (type as IslandBriefKind) : null);
const dateOf = (at: string | null | undefined): string | null => (at && !Number.isNaN(Date.parse(at)) ? at : null);
const whoOf = (person: Person): string | null => {
  const name = person?.name?.trim();
  if (!name) return null;
  const title = person?.title?.trim();
  return title ? `${name} (${title})` : name;
};

function briefLines(lines: SummaryLine[] | undefined, limit: number, withWho: boolean): IslandBriefLine[] {
  return (lines ?? [])
    .map((line): IslandBriefLine => {
      const shown: IslandBriefLine = { text: (line.text ?? "").trim(), type: kindOf(line.type), at: dateOf(line.occurred_at) };
      return withWho ? { ...shown, who: whoOf(line.with) } : shown;
    })
    .filter((line) => line.text)
    .slice(0, limit);
}

function companyBrief(activity: Activity): IslandCompanyBrief | null {
  const others = activity.company_interactions ?? [];
  if (!others.length) return null;
  const newest = others[0];
  const people = new Set(others.map((item) => whoOf(item.with)).filter(Boolean));
  return {
    name: activity.company?.name?.trim() || null,
    latest: { type: kindOf(newest.type), at: dateOf(newest.occurred_at), who: whoOf(newest.with) },
    people: people.size,
    lines: briefLines(activity.summary?.company_lines, ISLAND_COMPANY_LINES, true),
  };
}

/** The recent-activity summary as the island shows it; null when it has nothing to say (the island does not grow). */
export function islandBrief(activity: Activity | null | undefined): IslandBrief | null {
  if (!activity) return null;
  const lines = briefLines(activity.summary?.lines, ISLAND_BRIEF_LINES, false);
  const company = companyBrief(activity);
  return lines.length || company ? { state: "ready", lines, company } : null;
}

export type CallingAccess = {
  /** The company's plan includes the dialer. */
  canDial: boolean;
  callerId: string | null;
};

export type DialIsland = {
  phase: "connecting" | "ringing" | "active" | "ended";
  name: string | null;
  phone: string;
  answeredAt: number | null;
  muted: boolean;
  /** Why an unanswered call ended, in the rep's language; null shows the island's own "Call ended". */
  message: string | null;
  /** What happened with the contact lately, kept for the whole call (the offer's brief when Call was pressed). */
  brief: IslandBriefLine[] | null;
  /** And with other people at its company. */
  companyBrief: IslandCompanyBrief | null;
};

export type CallCommand =
  | { kind: "dial" }
  | { kind: "hangup" }
  | { kind: "mute"; muted: boolean }
  | { kind: "digit"; digit: string }
  | { kind: "open-calling" };

/** How long the island shows why an unanswered call ended. */
export const ENDED_HOLD_MS = 4000;

export function onScreenFromPreview(preview: CallPreview | null | undefined, access: CallingAccess): OnScreen | null {
  if (!access.canDial || !preview?.record || !preview.provider) return null;
  const crmLabel = CALLABLE_CRMS[preview.provider];
  if (!crmLabel) return null;
  const base = { provider: preview.provider, crmLabel, callerId: access.callerId };
  const callee = preview.callee;
  if (!callee) {
    return (preview.contacts_count ?? 0) > 1 ? { ...base, name: null, phone: null, state: "needs_contact" } : null;
  }
  const shown = { ...base, name: callee.name, phone: callee.phone };
  if (!callee.phone) return { ...shown, state: "no_phone" };
  if (!access.callerId) return { ...shown, state: "no_caller_id" };
  return { ...shown, state: "callable" };
}

export function dialTargetFor(preview: CallPreview | null | undefined, access: CallingAccess): DialTarget | null {
  const onScreen = onScreenFromPreview(preview, access);
  const callee = preview?.callee;
  if (onScreen?.state !== "callable" || !callee?.phone || !access.callerId) return null;
  return {
    to: callee.phone,
    name: callee.name,
    contactId: callee.contact_id,
    dealId: preview?.record?.object_type === "deal" ? preview.record.record_id : null,
    callerId: access.callerId,
  };
}

export function dialIsland(state: CallEngineState, brief: IslandCallBrief | null = null): DialIsland | null {
  const target = state.target;
  if (!target) return null;
  const shown = { name: target.name, phone: target.to, answeredAt: state.answeredAt, muted: state.muted };
  if (isCallUp(state)) {
    return {
      ...shown,
      phase: state.phase as DialIsland["phase"],
      message: null,
      brief: brief?.lines.length ? brief.lines : null,
      companyBrief: brief?.company ?? null,
    };
  }
  // An answered call carries on as the recording → post-call card; only a missed one stays here.
  if (isCallEnded(state) && !state.answered) {
    return { ...shown, phase: "ended", message: state.outcome ?? state.error, brief: null, companyBrief: null };
  }
  return null;
}

const DIGIT = /^digit:([0-9*#])$/;

export function parseCallCommand(raw: string): CallCommand | null {
  if (raw === "dial" || raw === "hangup" || raw === "open-calling") return { kind: raw };
  if (raw === "mute" || raw === "unmute") return { kind: "mute", muted: raw === "mute" };
  const digit = DIGIT.exec(raw);
  return digit ? { kind: "digit", digit: digit[1] } : null;
}

type CallerIdRow = {
  phoneNumber: string;
  status?: string | null;
  source?: string | null;
  isDefault?: boolean | null;
  callBlocked?: boolean | null;
};

/** The verified number a call goes out from: the default one, else the first (same rule as the dock). */
export function outgoingCallerId(callerIds: CallerIdRow[] | null | undefined): string | null {
  const verified = (callerIds ?? []).filter((c) => c.status === "verified" && c.source !== "twilio" && !c.callBlocked);
  return (verified.find((c) => c.isDefault) ?? verified[0])?.phoneNumber || null;
}

const HUBSPOT_RECORD = /^https:\/\/app(?:-[a-z0-9]+)?\.hubspot\.com\/contacts\/(\d+)\/record\/(0-\d+)\/(\d+)/i;
const HUBSPOT_LEGACY = /^https:\/\/app(?:-[a-z0-9]+)?\.hubspot\.com\/contacts\/(\d+)\/(contact|company|deal)\/(\d+)/i;
const LEGACY_TYPES: Record<string, string> = { contact: "0-1", company: "0-2", deal: "0-3" };

/**
 * Which CRM record a page is, as a key: the same for every view of one record (tabs, query strings), so the island's
 * offer stays put while the rep moves around inside it, and changes the moment the record does. Same URL shapes as
 * backend/app/services/live_calls/crm_url.py; null for anything else (the backend still decides who to call).
 */
export function crmRecordKey(url: string): string | null {
  const record = HUBSPOT_RECORD.exec(url);
  if (record) return `hubspot:${record[1]}:${record[2]}:${record[3]}`;
  const legacy = HUBSPOT_LEGACY.exec(url);
  if (legacy) return `hubspot:${legacy[1]}:${LEGACY_TYPES[legacy[2].toLowerCase()]}:${legacy[3]}`;
  return null;
}
