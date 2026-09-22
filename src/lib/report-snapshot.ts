/** The report page shows the stored snapshot. A missing close is not zero. */

export type ReportSnapshot = {
  metrics: {
    attempts: number;
    connected_calls: number;
    meetings_agreed: number;
    deals_won: number | null;
    adherence: number | null;
  };
  coverage: { crm_outcomes: string };
  coaching: string | null;
  examples?: string[];
};

export function bellCount(unread: number | null | undefined): string | null {
  if (unread == null || unread < 1) return null;
  return String(unread);
}

export function nullableMetricLabel(value: number | null, unavailable: string): string {
  return value === null ? unavailable : String(value);
}

export function reportExampleLinks(snapshot: ReportSnapshot): string[] {
  return (snapshot.examples ?? []).filter(Boolean).map((memoId) => `/dashboard/memos/${memoId}`);
}

export function reportSurface(snapshot: ReportSnapshot, unavailable: string) {
  const won = snapshot.metrics.deals_won;
  return {
    attempts: snapshot.metrics.attempts,
    connected: snapshot.metrics.connected_calls,
    meetings: snapshot.metrics.meetings_agreed,
    wonLabel: nullableMetricLabel(won, unavailable),
    adherenceLabel: nullableMetricLabel(snapshot.metrics.adherence, unavailable),
    coaching: snapshot.coaching,
    exampleLinks: reportExampleLinks(snapshot),
  };
}
