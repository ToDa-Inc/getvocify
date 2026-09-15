import type { Memo } from "@/features/memos/types";
import type { CrmCallRecording } from "@/features/recordings/types";

export const ACTIVITY_PAGE_SIZE = 3;
export const ACTIVITY_EXPAND_SIZE = 5;

export type ActivityItem =
  | { kind: "recording"; id: string; sortMs: number; recording: CrmCallRecording }
  | { kind: "memo"; id: string; sortMs: number; memo: Memo };

function toSortMs(value: string | number | null | undefined): number {
  if (value == null || value === "") return 0;
  if (typeof value === "number" && Number.isFinite(value)) {
    return value < 1e12 ? value * 1000 : value;
  }
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

function isLinkedMemo(
  memo: Pick<Memo, "id" | "hubspotEngagementId">,
  listed: CrmCallRecording[],
): boolean {
  const memoId = String(memo.id || "");
  const engagementId = String(memo.hubspotEngagementId || "");
  return listed.some((recording) => {
    const linkedMemo = String(recording.memo_id || "");
    const callId = String(recording.call_id || "");
    return (
      (memoId && linkedMemo === memoId) ||
      (engagementId && callId === engagementId)
    );
  });
}

export function mergeActivityItems({
  recordings = [],
  memos = [],
}: {
  recordings?: CrmCallRecording[];
  memos?: Array<Pick<Memo, "id" | "createdAt" | "hubspotEngagementId"> & Partial<Memo>>;
}): ActivityItem[] {
  const listed = (recordings || []).filter((row) => row && row.has_recording);
  const calls: ActivityItem[] = listed.map((recording) => ({
    kind: "recording",
    id: recording.call_id,
    sortMs: toSortMs(recording.timestamp ?? recording.timestamp_ms),
    recording,
  }));
  const vocify: ActivityItem[] = (memos || [])
    .filter((memo) => memo?.id && !isLinkedMemo(memo, listed))
    .map((memo) => ({
      kind: "memo",
      id: String(memo.id),
      sortMs: toSortMs(memo.createdAt),
      memo: memo as Memo,
    }));
  return [...calls, ...vocify].sort((a, b) => (b.sortMs || 0) - (a.sortMs || 0));
}

export function nextVisibleCount(
  current: number,
  total: number,
  pageSize = ACTIVITY_EXPAND_SIZE,
): number {
  const from = Number(current);
  const start = Number.isFinite(from) && from > 0 ? from : ACTIVITY_PAGE_SIZE;
  return Math.min(Math.max(Number(total) || 0, 0), start + pageSize);
}

export function shouldPeekNextActivity(
  visibleCount: number,
  total: number,
  pageSize = ACTIVITY_PAGE_SIZE,
): boolean {
  return visibleCount <= pageSize && Number(total) > visibleCount;
}

export function activityEmptyMessage({
  viewingTeammate,
  mine,
  canViewCompany,
}: {
  viewingTeammate: boolean;
  mine: boolean;
  canViewCompany: boolean;
}): string {
  if (viewingTeammate) {
    return "No activity for this teammate. Try All to see every labeled conversation.";
  }
  if (canViewCompany && mine) {
    return "No activity of yours yet. Try All to see every labeled conversation.";
  }
  return "No activity yet. Record your first one above.";
}
