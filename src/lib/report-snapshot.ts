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
};

export function bellCount(unread: number | null | undefined): string | null {
  if (unread == null || unread < 1) return null;
  return String(unread);
}

export function nullableMetricLabel(value: number | null): string {
  return value === null ? "No disponible" : String(value);
}

export function reportSurface(snapshot: ReportSnapshot) {
  const won = snapshot.metrics.deals_won;
  return {
    attempts: snapshot.metrics.attempts,
    connected: snapshot.metrics.connected_calls,
    meetings: snapshot.metrics.meetings_agreed,
    wonLabel: nullableMetricLabel(won),
    adherenceLabel: nullableMetricLabel(snapshot.metrics.adherence),
    coaching: snapshot.coaching,
  };
}
