/** The report page shows the stored snapshot. A missing close is not zero. */

import type { ProductTranslations } from "./product-catalog";

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

export type ReportMetricCellKey =
  | "attempts"
  | "connected_calls"
  | "meetings_agreed"
  | "deals_won"
  | "adherence";

export type ReportMetricLabelKey = Pick<
  ProductTranslations,
  | "teamActivityAttempts"
  | "teamActivityConnected"
  | "teamActivityMeetings"
  | "teamOutcomesWon"
  | "teamHeadingAdherence"
>[keyof Pick<
  ProductTranslations,
  | "teamActivityAttempts"
  | "teamActivityConnected"
  | "teamActivityMeetings"
  | "teamOutcomesWon"
  | "teamHeadingAdherence"
>];

const METRIC_LABEL_KEYS: Record<ReportMetricCellKey, ReportMetricLabelKey> = {
  attempts: "teamActivityAttempts",
  connected_calls: "teamActivityConnected",
  meetings_agreed: "teamActivityMeetings",
  deals_won: "teamOutcomesWon",
  adherence: "teamHeadingAdherence",
};

const ACTIVITY_TABLE_KEYS: ReportMetricCellKey[] = [
  "attempts",
  "connected_calls",
  "meetings_agreed",
];

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

/** Same strings as backend `snapshot_metric_cells` / email HTML table cells. */
export function snapshotMetricCells(snapshot: ReportSnapshot, unavailable: string): Record<ReportMetricCellKey, string> {
  const metrics = snapshot.metrics;
  return {
    attempts: String(metrics.attempts),
    connected_calls: String(metrics.connected_calls),
    meetings_agreed: String(metrics.meetings_agreed),
    deals_won: nullableMetricLabel(metrics.deals_won, unavailable),
    adherence: nullableMetricLabel(metrics.adherence, unavailable),
  };
}

export function ratioBarWidth(numerator: number, denominator: number): number | null {
  if (denominator <= 0) return null;
  return (numerator / denominator) * 100;
}

export type ReportPageRow = {
  cellKey: ReportMetricCellKey;
  labelKey: ReportMetricLabelKey;
  value: string;
};

export type ReportPageBars = {
  conversationsOfAttempts: number | null;
  meetingsOfAttempts: number | null;
};

export function reportPagePresentation(
  snapshot: ReportSnapshot,
  options: { weekly: boolean; unavailable: string },
): {
  rows: ReportPageRow[];
  bars: ReportPageBars | null;
  activityTable: ReportPageRow[] | null;
  coaching: string | null;
  exampleLinks: string[];
} {
  const cells = snapshotMetricCells(snapshot, options.unavailable);
  const rows: ReportPageRow[] = (Object.keys(METRIC_LABEL_KEYS) as ReportMetricCellKey[]).map((cellKey) => ({
    cellKey,
    labelKey: METRIC_LABEL_KEYS[cellKey],
    value: cells[cellKey],
  }));
  const { attempts, connected_calls, meetings_agreed } = snapshot.metrics;
  const bars = options.weekly
    ? {
        conversationsOfAttempts: ratioBarWidth(connected_calls, attempts),
        meetingsOfAttempts: ratioBarWidth(meetings_agreed, attempts),
      }
    : null;
  const activityTable = options.weekly
    ? ACTIVITY_TABLE_KEYS.map((cellKey) => ({
        cellKey,
        labelKey: METRIC_LABEL_KEYS[cellKey],
        value: cells[cellKey],
      }))
    : null;
  return {
    rows,
    bars,
    activityTable,
    coaching: snapshot.coaching,
    exampleLinks: reportExampleLinks(snapshot),
  };
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
