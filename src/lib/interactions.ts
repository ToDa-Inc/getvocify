import type { MemoFilters } from "@/features/memos/types";

export type Channel = "call" | "meeting" | "visit" | "voice_note";
export type TypeOption = { key: string; label: string; scored: boolean };

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
    .map((key) => ({ key, label: details?.[key]?.label || labelOf(key), scored: true }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return [...types, { key: INTERNAL_KEY, label: internalLabel, scored: false }];
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
