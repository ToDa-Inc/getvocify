/** The report page shows the stored snapshot. A missing close is not zero. */

import type { ProductTranslations } from "./product-catalog";

export type ReportDay = {
  date: string;
  connected_calls: number | null;
  meetings_agreed: number | null;
  covered: boolean;
};

export type ReportObjection = { name: string; count: number };

export type ReportChannelCounts = Partial<Record<"call" | "meeting" | "visit", number>>;

export type ReportSnapshot = {
  metrics: {
    attempts: number;
    connected_calls: number;
    meetings_agreed: number;
    deals_won: number | null;
    adherence: number | null;
    channels?: ReportChannelCounts;
  };
  coverage: { crm_outcomes: string; objections?: string };
  coaching: string | null;
  examples?: string[];
  scope?: "self" | "team";
  report_type?: "daily" | "weekly";
  period_start?: string;
  period_end?: string;
  timezone?: string;
  generated_at?: string;
  series?: ReportDay[];
  objections?: ReportObjection[] | null;
  adherence_steps?: { met: number; applicable: number } | null;
  sample_limited?: boolean;
  adherence_trend?: ReportAdherenceTrend | null;
};

export type ReportTrendCell = { state: string; met: number; applicable: number; sample_limited: boolean };

export type ReportAdherenceTrend = {
  weeks: string[];
  team: ReportTrendCell[];
  reps: { name: string; weeks: ReportTrendCell[] }[];
};

function trendCellLabel(cell: ReportTrendCell, copy: { unscored: string; stepsTemplate: string }): string {
  if (cell.state === "gap") return "—";
  if (cell.state !== "scored") return copy.unscored;
  const steps = copy.stepsTemplate.replace("{met}", String(cell.met)).replace("{applicable}", String(cell.applicable));
  return cell.sample_limited ? `${steps}*` : steps;
}

/** Same cells as the team email's «Adherencia por semana» table. */
export function reportAdherenceTrend(
  snapshot: ReportSnapshot,
  copy: { team: string; unscored: string; stepsTemplate: string },
): { weeks: string[]; rows: { name: string; cells: string[] }[]; sampleLimited: boolean } | null {
  const trend = snapshot.adherence_trend;
  if (!trend?.weeks?.length) return null;
  const series = [
    { name: copy.team, weeks: trend.team ?? [] },
    ...(trend.reps ?? []).map((rep) => ({ name: rep.name, weeks: rep.weeks ?? [] })),
  ];
  return {
    weeks: trend.weeks,
    rows: series.map((row) => ({ name: row.name, cells: row.weeks.map((cell) => trendCellLabel(cell, copy)) })),
    sampleLimited: series.some((row) => row.weeks.some((cell) => cell.sample_limited)),
  };
}

export type ReportMetricCellKey =
  | "attempts"
  | "connected_calls"
  | "meetings_agreed"
  | "deals_won"
  | "adherence";

export type ReportMetricLabelKey = keyof Pick<
  ProductTranslations,
  | "teamActivityAttempts"
  | "teamActivityConnected"
  | "teamActivityMeetings"
  | "teamOutcomesWon"
  | "teamHeadingAdherence"
>;

const METRIC_LABEL_KEYS: Record<ReportMetricCellKey, ReportMetricLabelKey> = {
  attempts: "teamActivityAttempts",
  connected_calls: "teamActivityConnected",
  meetings_agreed: "teamActivityMeetings",
  deals_won: "teamOutcomesWon",
  adherence: "teamHeadingAdherence",
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

function adherenceLabel(snapshot: ReportSnapshot, unavailable: string, stepsTemplate?: string): string {
  const steps = snapshot.adherence_steps;
  if (stepsTemplate && steps && steps.applicable > 0) {
    return stepsTemplate.replace("{met}", String(steps.met)).replace("{applicable}", String(steps.applicable));
  }
  return nullableMetricLabel(snapshot.metrics.adherence, unavailable);
}

/** Same strings as backend `snapshot_metric_cells` / email HTML table cells. */
export function snapshotMetricCells(
  snapshot: ReportSnapshot,
  unavailable: string,
  stepsTemplate?: string,
): Record<ReportMetricCellKey, string> {
  const metrics = snapshot.metrics;
  return {
    attempts: String(metrics.attempts),
    connected_calls: String(metrics.connected_calls),
    meetings_agreed: String(metrics.meetings_agreed),
    deals_won: nullableMetricLabel(metrics.deals_won, unavailable),
    adherence: adherenceLabel(snapshot, unavailable, stepsTemplate),
  };
}

export type ReportPageRow = {
  cellKey: ReportMetricCellKey;
  labelKey: ReportMetricLabelKey;
  value: string;
};

export type ReportPageDay = {
  date: string;
  connected: number | null;
  meetings: number | null;
  covered: boolean;
};

export type ReportChannelCopy = {
  call: { one: string; other: string };
  meeting: { one: string; other: string };
  visit: { one: string; other: string };
};

const CHANNEL_ORDER = ["call", "meeting", "visit"] as const;

function channelPart(count: number, words: { one: string; other: string }): string {
  return count === 1 ? words.one : words.other.replace("{count}", String(count));
}

/** Same breakdown as backend `channels_text` / email «Conversaciones» row. */
export function channelsText(snapshot: ReportSnapshot, copy: ReportChannelCopy): string | null {
  const channels = snapshot.metrics.channels;
  if (!channels || typeof channels !== "object") return null;
  const parts = CHANNEL_ORDER.flatMap((key) => {
    const count = Number(channels[key] ?? 0);
    if (count < 1) return [];
    return [channelPart(count, copy[key])];
  });
  return parts.length ? parts.join(" · ") : null;
}

export function reportPagePresentation(
  snapshot: ReportSnapshot,
  options: { unavailable: string; stepsTemplate?: string; channelCopy?: ReportChannelCopy },
): {
  rows: ReportPageRow[];
  days: ReportPageDay[];
  objections: ReportObjection[] | null;
  coaching: string | null;
  exampleLinks: string[];
  channelsLine: string | null;
} {
  const cells = snapshotMetricCells(snapshot, options.unavailable, options.stepsTemplate);
  const rows: ReportPageRow[] = (Object.keys(METRIC_LABEL_KEYS) as ReportMetricCellKey[]).map((cellKey) => ({
    cellKey,
    labelKey: METRIC_LABEL_KEYS[cellKey],
    value: cells[cellKey],
  }));
  const days = (snapshot.series ?? []).map((day) => ({
    date: day.date,
    connected: day.covered ? day.connected_calls : null,
    meetings: day.covered ? day.meetings_agreed : null,
    covered: day.covered,
  }));
  return {
    rows,
    days,
    objections: snapshot.objections?.length ? snapshot.objections : null,
    coaching: snapshot.coaching,
    exampleLinks: reportExampleLinks(snapshot),
    channelsLine: options.channelCopy ? channelsText(snapshot, options.channelCopy) : null,
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

export type ReportTitleKey = "reportTitleDaily" | "reportTitleWeekly" | "reportTitleTeam";

export function reportTitleKey(report: { report_type?: string | null; scope?: string | null }): ReportTitleKey {
  if (report.scope === "team") return "reportTitleTeam";
  return report.report_type === "weekly" ? "reportTitleWeekly" : "reportTitleDaily";
}

export type BellReportItem = {
  id: string;
  report_id: string;
  report_type: "daily" | "weekly";
  scope: "self" | "team";
  period_start: string;
  read_at: string | null;
};

export type VocifyActivityItem = {
  kind: "crm_updated" | "meeting_stage";
  memo_id: string;
  subject: string | null;
  resources: string[];
  at: string;
};

export type NotificationsResponse = {
  unread: number | null;
  items: BellReportItem[];
  activity?: VocifyActivityItem[] | null;
};

type BellCopy = {
  bellCrmUpdated: string;
  bellMeetingStage: string;
  bellBecause: string;
  bellBecauseUnnamed: string;
  listAnd: string;
  crmResources: Record<string, string>;
};

export function joinList(items: string[], and: string): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} ${and} ${items[items.length - 1]}`;
}

export function bellActivityText(item: VocifyActivityItem, copy: BellCopy) {
  const resources = item.resources.map((name) => copy.crmResources[name] ?? name);
  const title = item.kind === "meeting_stage"
    ? copy.bellMeetingStage
    : copy.bellCrmUpdated.replace("{resources}", joinList(resources, copy.listAnd));
  const why = item.subject ? copy.bellBecause.replace("{subject}", item.subject) : copy.bellBecauseUnnamed;
  return { title, why, href: `/dashboard/memos/${item.memo_id}` };
}
