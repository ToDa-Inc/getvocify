export type HistoryGroupKey = "today" | "yesterday" | "week" | "older";

const ORDER: HistoryGroupKey[] = ["today", "yesterday", "week", "older"];

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** Conversations grouped the way people look for them: today, yesterday, this week, older. Order inside a group is kept. */
export function groupByDay<T extends { updated_at: string | null }>(rows: T[], now: Date): { key: HistoryGroupKey; rows: T[] }[] {
  const today = startOfDay(now);
  const buckets = new Map<HistoryGroupKey, T[]>();
  for (const row of rows) {
    const stamp = row.updated_at ? new Date(row.updated_at).getTime() : Number.NaN;
    const days = Number.isNaN(stamp) ? Number.POSITIVE_INFINITY : Math.round((today - startOfDay(new Date(stamp))) / 86_400_000);
    const key: HistoryGroupKey = days <= 0 ? "today" : days === 1 ? "yesterday" : days < 7 ? "week" : "older";
    buckets.set(key, [...(buckets.get(key) ?? []), row]);
  }
  return ORDER.filter((key) => buckets.has(key)).map((key) => ({ key, rows: buckets.get(key) as T[] }));
}
