import type { MemoFilters } from "@/features/memos/types";
import { memoContactName } from "./copilot-note.ts";
import { motionLabel } from "./motion-label.ts";

export type Channel = "call" | "meeting" | "visit" | "voice_note";
export const CHANNELS: Channel[] = ["call", "meeting", "visit", "voice_note"];
export type PlaybookStatus = "published" | "paused" | "draft" | "missing" | "importing";
/** `status` is the type's playbook state from GET /playbooks; "Interna" has none (it has no playbook). */
export type TypeOption = { key: string; label: string; scored: boolean; status?: PlaybookStatus };

const STATUSES: readonly string[] = ["published", "paused", "draft", "missing", "importing"];

/** The reserved type for internal conversations: it has no playbook and is never scored. */
export const INTERNAL_KEY = "internal";

type PlaybooksPayload = {
  motions?: Record<string, unknown>;
  details?: Record<string, { label?: string | null } | undefined>;
};

/**
 * The type filter and retag choices, from GET /playbooks. Deleted types are not in `motions`, so they
 * never show. A stored label wins; otherwise `labelOf` names the catalog type (the caller owns the copy).
 * Alphabetical by label, then `internal`, which is not a playbook and is always offered.
 */
export function typeOptions(
  playbooksPayload: unknown,
  internalLabel: string,
  labelOf: (key: string) => string = (key) => key,
): TypeOption[] {
  const { motions, details } = (playbooksPayload ?? {}) as PlaybooksPayload;
  const types = Object.keys(motions ?? {})
    .filter((key) => key !== INTERNAL_KEY)
    .map((key) => {
      const status = motions?.[key];
      return {
        key,
        label: details?.[key]?.label || labelOf(key),
        scored: true,
        ...(typeof status === "string" && STATUSES.includes(status) && { status: status as PlaybookStatus }),
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
  return [...types, { key: INTERNAL_KEY, label: internalLabel, scored: false }];
}

/**
 * What a memo can be retagged to: types with a live playbook (a draft has no version to score
 * against and the API refuses it; a paused one is switched off), then "Interna", which needs none.
 * Keeps the alphabetical order of `typeOptions`.
 */
export function retagOptions(options: TypeOption[]): TypeOption[] {
  const types = options.filter((option) => option.key !== INTERNAL_KEY && option.status === "published");
  const internal = options.filter((option) => option.key === INTERNAL_KEY);
  return [...types, ...internal];
}

/**
 * The author filter the Interacciones page opens on: a manager sees everyone unless `?author=`
 * names a person (rep detail links here); a member's list is already their own.
 */
export function interactionsAuthor(canViewCompany: boolean, authorParam: string | null | undefined): string | null {
  return canViewCompany ? authorParam || null : null;
}

type TypeNameCopy = { typeLabels: Record<string, string>; motions: Record<string, string>; internal: string };

/** A type's name on the memo detail: Interna from the catalog, else the stored label, the catalog label, the key. */
export function memoTypeName(key: string, label: string | null | undefined, copy: TypeNameCopy): string {
  if (key === INTERNAL_KEY) return copy.internal;
  return label || copy.typeLabels[key] || motionLabel(key, copy.motions);
}

/** "Evaluada como Demo", or "Interna · no se puntúa" for an internal memo, which has no playbook. */
export function memoTypeLine(key: string, name: string, copy: { memoPlaybook: string; memoPlaybookInternal: string }): string {
  return key === INTERNAL_KEY ? copy.memoPlaybookInternal : copy.memoPlaybook.replace("{name}", name);
}

/** The chip on a feed row: null without a type; a type that is no longer listed shows its key. */
export function typeChip(
  memo: { salesMotionKey?: string | null },
  options: TypeOption[],
): { key: string; label: string } | null {
  const key = memo.salesMotionKey;
  if (!key) return null;
  return { key, label: options.find((option) => option.key === key)?.label ?? key };
}

/** One row more than the page is asked for, so the feed knows whether there is a next page. */
export function feedQuery(
  state: { channel: Channel | "all"; typeKey: string | "all"; authorUserId?: string; page: number },
  pageSize: number,
): MemoFilters {
  return {
    limit: pageSize + 1,
    offset: state.page * pageSize,
    ...(state.channel !== "all" && { interactionKind: state.channel }),
    ...(state.typeKey !== "all" && { salesMotionKey: state.typeKey }),
    ...(state.authorUserId && { authorUserId: state.authorUserId }),
  };
}

export function pageOf<T>(rows: T[], pageSize: number): { items: T[]; hasMore: boolean } {
  return { items: rows.slice(0, pageSize), hasMore: rows.length > pageSize };
}

/** The row's channel chip: one of the four channels, or none for anything else. */
export function channelOf(kind: string | null | undefined): Channel | null {
  return CHANNELS.includes(kind as Channel) ? (kind as Channel) : null;
}

export type RowStatus = "synced" | "review" | "processing" | "failed" | "voicemail" | "no_answer";

const PROCESSING = new Set(["uploading", "transcribing", "extracting", "pending_transcript"]);
const BUSY = new Set(["uploading", "transcribing", "extracting"]);

/** What the status pill says. A rejected memo shows none. */
export function rowStatus(memo: { status: string; screeningOutcome?: string | null }): RowStatus | null {
  if (memo.status === "pending_review") {
    if (memo.screeningOutcome === "voicemail") return "voicemail";
    if (memo.screeningOutcome === "no_response") return "no_answer";
    return "review";
  }
  if (memo.status === "approved") return "synced";
  if (memo.status === "failed") return "failed";
  if (PROCESSING.has(memo.status)) return "processing";
  return null;
}

/** The feed polls only while a row on screen is still being processed. */
export function feedBusy(rows: { status: string }[]): boolean {
  return rows.some((row) => BUSY.has(row.status));
}

type Named = { extraction?: { contactName?: string | null; companyName?: string | null } | null };


export type SummaryParts = { heading: string | null; line: string | null };

const plain = (text: string) =>
  text
    .replace(/\*\*|__|`/g, "")
    .replace(/\s+/g, " ")
    .trim();

/** A summary is markdown: its first heading is the topic, its first bullet the line worth reading. */
export function summaryParts(markdown: string | null | undefined): SummaryParts {
  let heading: string | null = null;
  let line: string | null = null;
  for (const raw of String(markdown ?? "").split("\n")) {
    const text = raw.trim();
    if (!text) continue;
    if (text.startsWith("#")) {
      const topic = plain(text.replace(/^#+/, ""));
      if (topic && !heading && !line) heading = topic;
      continue;
    }
    const item = plain(text.replace(/^([-*•]|\d+[.)])\s*/, ""));
    if (item) {
      line = item;
      break;
    }
  }
  return { heading, line };
}

/** What a row is about: the person and company when known, otherwise the summary's topic. */
export function rowHeadline(
  memo: Named & { extraction?: { summary?: string | null } | null },
  fallback: string,
): { title: string; preview: string | null } {
  const contact = memoContactName(memo);
  const company = String(memo.extraction?.companyName || "").trim();
  const parts = summaryParts(memo.extraction?.summary);
  const named = [contact, company && company.toLowerCase() !== contact.toLowerCase() ? company : ""].filter(Boolean).join(" · ");
  if (named) return { title: named, preview: parts.line ?? parts.heading };
  if (parts.heading) return { title: parts.heading, preview: parts.line };
  if (parts.line) return { title: parts.line, preview: null };
  return { title: fallback, preview: null };
}

const capital = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);
const dayKey = (at: Date) => `${at.getFullYear()}-${at.getMonth()}-${at.getDate()}`;

/** Newest-first rows under "Hoy", "Ayer" and short dates, in the order they come. Bad dates go last. */
export function groupByDay<T extends { createdAt: string }>(
  items: T[],
  now: Date,
  locale: string,
): { key: string; label: string; items: T[] }[] {
  const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  const groups = new Map<string, { key: string; label: string; items: T[] }>();
  const undated: T[] = [];
  for (const item of items) {
    const at = new Date(item.createdAt);
    if (Number.isNaN(at.getTime())) {
      undated.push(item);
      continue;
    }
    const key = dayKey(at);
    if (!groups.has(key)) {
      const label =
        key === dayKey(now)
          ? relative.format(0, "day")
          : key === dayKey(yesterday)
            ? relative.format(-1, "day")
            : new Intl.DateTimeFormat(locale, {
                weekday: "short",
                day: "numeric",
                month: "short",
                ...(at.getFullYear() !== now.getFullYear() && { year: "numeric" }),
              }).format(at);
      groups.set(key, { key, label: capital(label.replace(/\.(?=\s|,|$)/g, "")), items: [] });
    }
    groups.get(key)!.items.push(item);
  }
  const out = [...groups.values()];
  if (undated.length) out.push({ key: "undated", label: "", items: undated });
  return out;
}

/** "17:05" / "5:05 PM", the way the viewer's language writes a time. Empty for a bad date. */
export function timeLabel(iso: string, locale: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(at);
}
