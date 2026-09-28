/**
 * Head of Sales phase 2 (docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md): pure helpers for
 * the manager-only part of the Team page. Numbers come from /team/adherence; nothing here
 * invents a value that the backend returned as null.
 */
import type { ProductTranslations } from "./product-catalog.ts";

export type HosPeriod = "week" | "month" | "last_30" | "quarter";
export type HosSalesRole = "all" | "sdr" | "ae";

export const HOS_PERIODS: readonly { value: HosPeriod; labelKey: keyof ProductTranslations }[] = [
  { value: "week", labelKey: "hosPeriodWeek" },
  { value: "month", labelKey: "hosPeriodMonth" },
  { value: "last_30", labelKey: "hosPeriodLast30" },
  { value: "quarter", labelKey: "hosPeriodQuarter" },
];

export type Activity = { attempts: number; connected: number; meetings: number };

export type HosRep = {
  userId: string;
  name: string;
  salesRole?: string | null;
  activity?: Activity;
  flows?: { sdr: number | null; ae: number | null };
};

/** Query string for /team/adherence. A member (visibility=team) sends only what it sent before. */
export function adherenceParams(input: {
  manager: boolean;
  period: HosPeriod;
  salesRole: HosSalesRole;
  userId: string | null;
  motion: string | null;
}): string {
  const params = new URLSearchParams();
  if (input.userId) params.set("user_id", input.userId);
  if (input.motion) params.set("motion", input.motion);
  if (input.manager) {
    params.set("period", input.period);
    if (input.salesRole !== "all") params.set("sales_role", input.salesRole);
  }
  return params.toString();
}

export type Delta = { text: string; direction: "up" | "down" | "flat" } | null;

/** Math.round sends -22.5 to -22 but 22.5 to 23: round the magnitude so a change's size
 * does not depend on its sign. */
function roundSymmetric(value: number): number {
  // Snap float noise first: (0.675 - 0.9) * 100 is -22.4999..., which is -22.5.
  const magnitude = Math.round(Math.abs(value) * 1e6) / 1e6;
  return Math.sign(value) * Math.round(magnitude);
}

export function countDelta(current: number | null | undefined, previous: number | null | undefined): Delta {
  if (current == null || previous == null) return null;
  if (!current && !previous) return null;
  if (!previous) return { text: "new", direction: "up" };
  const pct = roundSymmetric(((current - previous) / previous) * 100);
  if (pct === 0) return { text: "0%", direction: "flat" };
  return { text: `${pct > 0 ? "+" : ""}${pct}%`, direction: pct > 0 ? "up" : "down" };
}

/** Rates change in percentage points. */
export function rateDelta(current: number | null | undefined, previous: number | null | undefined): Delta {
  if (current == null || previous == null) return null;
  const pts = roundSymmetric((current - previous) * 100);
  if (pts === 0) return { text: "0 pts", direction: "flat" };
  return { text: `${pts > 0 ? "+" : ""}${pts} pts`, direction: pts > 0 ? "up" : "down" };
}

export function shareOf(part: number, whole: number): number | null {
  return whole > 0 ? part / whole : null;
}

export function percentText(rate: number | null | undefined): string {
  return rate == null ? "—" : `${Math.round(rate * 100)}%`;
}

export type RepActivityRow = {
  userId: string;
  name: string;
  salesRole: string | null;
  attempts: number;
  connected: number;
  meetings: number;
  connectionRate: number | null;
  flows?: { sdr: number | null; ae: number | null };
};

/** Alphabetical, like the rest of the Team page: this is not a leaderboard. */
export function repActivityRows(reps: HosRep[]): RepActivityRow[] {
  return [...reps]
    .sort((a, b) => a.name.localeCompare(b.name, "es"))
    .map((rep) => {
      const a = rep.activity ?? { attempts: 0, connected: 0, meetings: 0 };
      return {
        userId: rep.userId,
        name: rep.name,
        salesRole: rep.salesRole ?? null,
        attempts: a.attempts,
        connected: a.connected,
        meetings: a.meetings,
        connectionRate: shareOf(a.connected, a.attempts),
        flows: rep.flows,
      };
    });
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((x, y) => x - y);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Median over people with at least one attempt (an idle seat is not the reference); total over all. */
export function teamActivityFooter(rows: RepActivityRow[]) {
  const active = rows.filter((row) => row.attempts > 0);
  const total = rows.reduce(
    (acc, row) => ({
      attempts: acc.attempts + row.attempts,
      connected: acc.connected + row.connected,
      meetings: acc.meetings + row.meetings,
    }),
    { attempts: 0, connected: 0, meetings: 0 },
  );
  const rates = active.map((row) => row.connectionRate).filter((r): r is number => r != null);
  return {
    median: {
      people: active.length,
      attempts: median(active.map((r) => r.attempts)),
      connected: median(active.map((r) => r.connected)),
      meetings: median(active.map((r) => r.meetings)),
      connectionRate: median(rates),
    },
    total: { ...total, connectionRate: shareOf(total.connected, total.attempts) },
  };
}

function csvCell(value: string | number | null): string {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function repActivityCsv(rows: RepActivityRow[], copy: ProductTranslations): string {
  const header = [copy.hosColName, copy.hosColRole, copy.hosColAttempts, copy.hosColConversations, copy.hosColConnection, copy.hosColMeetings];
  const lines = rows.map((row) =>
    [
      row.name,
      row.salesRole,
      row.attempts,
      row.connected,
      row.connectionRate == null ? null : Math.round(row.connectionRate * 1000) / 10,
      row.meetings,
    ]
      .map(csvCell)
      .join(","),
  );
  return [header.map(csvCell).join(","), ...lines].join("\n");
}

export type ProcessHealthVerdict =
  | "playbook_underperforms"
  | "coach_reps"
  | "playbook_works"
  | "no_difference"
  | "no_comparison"
  | "insufficient_data"
  | "goal_not_measurable";

export type ProcessHealthFlow = {
  motion: string;
  goal: string | null;
  scored: number;
  verdict: ProcessHealthVerdict;
  matrix: { follows_goal: number; follows_no_goal: number; deviates_goal: number; deviates_no_goal: number } | null;
  follow_share?: number | null;
  follows_goal_rate?: number | null;
  deviates_goal_rate?: number | null;
  needed?: number;
};

/** process: the playbook needs fixing · rep: people need coaching · ok · neutral: no verdict. */
export type ProcessTone = "process" | "rep" | "ok" | "neutral";

const VERDICT_COPY: Record<ProcessHealthVerdict, { tone: ProcessTone; title: keyof ProductTranslations; detail: keyof ProductTranslations }> = {
  playbook_underperforms: { tone: "process", title: "hosVerdictUnderperformsTitle", detail: "hosVerdictUnderperformsDetail" },
  coach_reps: { tone: "rep", title: "hosVerdictCoachTitle", detail: "hosVerdictCoachDetail" },
  playbook_works: { tone: "ok", title: "hosVerdictWorksTitle", detail: "hosVerdictWorksDetail" },
  no_difference: { tone: "process", title: "hosVerdictNoDifferenceTitle", detail: "hosVerdictNoDifferenceDetail" },
  no_comparison: { tone: "neutral", title: "hosVerdictNoComparisonTitle", detail: "hosVerdictNoComparisonDetail" },
  insufficient_data: { tone: "neutral", title: "hosVerdictInsufficientTitle", detail: "hosVerdictInsufficientDetail" },
  goal_not_measurable: { tone: "neutral", title: "hosVerdictNotMeasurableTitle", detail: "hosVerdictNotMeasurableDetail" },
};

export function processHealthView(flow: ProcessHealthFlow, copy: ProductTranslations) {
  const entry = VERDICT_COPY[flow.verdict] ?? VERDICT_COPY.insufficient_data;
  const detail = String(copy[entry.detail])
    .replace("{follows}", percentText(flow.follows_goal_rate))
    .replace("{deviates}", percentText(flow.deviates_goal_rate))
    .replace("{share}", percentText(flow.follow_share))
    .replace("{needed}", String(flow.needed ?? 0));
  return { tone: entry.tone, title: String(copy[entry.title]), detail };
}

export const HOS_DEFAULT_PERIOD: HosPeriod = "month";

export type DiagnosisTone = ProcessTone;
export type Diagnosis = {
  tone: DiagnosisTone;
  key:
    | "hosDiagNoActivity"
    | "hosDiagPlaybook"
    | "hosDiagPlaybookNoEffect"
    | "hosDiagCoach"
    | "hosDiagNoProcess"
    | "hosDiagWorks"
    | "hosDiagCollecting";
  motion: string | null;
  href: string | null;
};

const PROCESS_HREF = "/dashboard/process";
const TEAM_HREF = "/dashboard/insights";

/** Resumen's one sentence (plan §3.1): is the problem the people or the process? Rules, not an LLM. */
export function summaryDiagnosis(input: {
  attempts: number | null;
  adherence: number | null;
  processHealth: ProcessHealthFlow[];
}): Diagnosis {
  const flows = input.processHealth ?? [];
  const find = (verdict: ProcessHealthVerdict) => flows.find((f) => f.verdict === verdict);
  if (!input.attempts) return { tone: "neutral", key: "hosDiagNoActivity", motion: null, href: null };
  const broken = find("playbook_underperforms");
  if (broken) return { tone: "process", key: "hosDiagPlaybook", motion: broken.motion, href: PROCESS_HREF };
  const flat = find("no_difference");
  if (flat) return { tone: "process", key: "hosDiagPlaybookNoEffect", motion: flat.motion, href: PROCESS_HREF };
  const coach = find("coach_reps");
  if (coach) return { tone: "rep", key: "hosDiagCoach", motion: coach.motion, href: TEAM_HREF };
  if (input.adherence == null) return { tone: "neutral", key: "hosDiagNoProcess", motion: null, href: PROCESS_HREF };
  const works = find("playbook_works");
  if (works) return { tone: "ok", key: "hosDiagWorks", motion: works.motion, href: null };
  return { tone: "neutral", key: "hosDiagCollecting", motion: null, href: PROCESS_HREF };
}

/** Short name for a flow inside a sentence: "SDR" / "AE" for the two role flows. */
export function flowShortName(motion: string | null, fallback: string): string {
  if (motion === "discovery") return "SDR";
  if (motion === "closing") return "AE";
  return fallback;
}
