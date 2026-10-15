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

/** The one step a rep works on this week (previous full week, same engine the rep sees). */
export type HosFocus = { step_id: string; label: string; rate: number | null };

export type HosRep = {
  userId: string;
  name: string;
  salesRole?: string | null;
  activity?: Activity;
  /** Only present when the request carried ?period=; null = no focus (going well or no data). */
  coaching_focus?: HosFocus | null;
  flows?: { sdr: number | null; ae: number | null };
};

/** Query string for /team/adherence. A member (visibility=team) sends only what it sent before. */
export function adherenceParams(input: {
  manager: boolean;
  period: HosPeriod;
  salesRole: HosSalesRole;
  userId: string | null;
  motion: string | null;
  /** Manager only: ask for each rep's coaching focus (the Equipo page, nobody else). */
  withFocus?: boolean;
}): string {
  const params = new URLSearchParams();
  if (input.userId) params.set("user_id", input.userId);
  if (input.motion) params.set("motion", input.motion);
  if (input.manager) {
    params.set("period", input.period);
    if (input.salesRole !== "all") params.set("sales_role", input.salesRole);
    if (input.withFocus) params.set("with_focus", "true");
  }
  return params.toString();
}

export function percentText(rate: number | null | undefined): string {
  return rate == null ? "—" : `${Math.round(rate * 100)}%`;
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

/** Where a process problem is fixed (the playbooks, in Ajustes) and where people are read (Equipo → Personas). */
export const PROCESS_HREF = "/dashboard/playbook";
const TEAM_HREF = "/dashboard/insights?tab=people";

/** Lower = more severe. Only verdicts that say something about the flow have an entry. */
const DIAGNOSIS_BY_VERDICT: Partial<Record<ProcessHealthVerdict, { severity: number; tone: DiagnosisTone; key: Diagnosis["key"]; href: string | null }>> = {
  playbook_underperforms: { severity: 0, tone: "process", key: "hosDiagPlaybook", href: PROCESS_HREF },
  no_difference: { severity: 1, tone: "process", key: "hosDiagPlaybookNoEffect", href: PROCESS_HREF },
  coach_reps: { severity: 2, tone: "rep", key: "hosDiagCoach", href: TEAM_HREF },
  playbook_works: { severity: 3, tone: "ok", key: "hosDiagWorks", href: null },
};

const MOTION_ORDER = ["discovery", "closing"];

/** Resumen's diagnosis (plan §3.1): is the problem the people or the process? One line per flow
 * with a verdict (SDR, AE; max 2), most severe first, so a second problem is never hidden.
 * Rules, not an LLM. */
export function summaryDiagnosis(input: {
  attempts: number | null;
  adherence: number | null;
  processHealth: ProcessHealthFlow[];
}): Diagnosis[] {
  if (!input.attempts) return [{ tone: "neutral", key: "hosDiagNoActivity", motion: null, href: null }];
  const seen = new Set<string>();
  const lines: { severity: number; order: number; diagnosis: Diagnosis }[] = [];
  for (const flow of input.processHealth ?? []) {
    const entry = DIAGNOSIS_BY_VERDICT[flow.verdict];
    if (!entry || seen.has(flow.motion)) continue;
    seen.add(flow.motion);
    const order = MOTION_ORDER.indexOf(flow.motion);
    lines.push({
      severity: entry.severity,
      order: order === -1 ? MOTION_ORDER.length : order,
      diagnosis: { tone: entry.tone, key: entry.key, motion: flow.motion, href: entry.href },
    });
  }
  lines.sort((a, b) => a.severity - b.severity || a.order - b.order);
  const picked = lines.slice(0, 2).map((line) => line.diagnosis);
  const hasProblem = picked.some((d) => d.tone !== "ok");
  if (!hasProblem && input.adherence == null) {
    return [{ tone: "neutral", key: "hosDiagNoProcess", motion: null, href: PROCESS_HREF }];
  }
  if (picked.length) return picked;
  return [{ tone: "neutral", key: "hosDiagCollecting", motion: null, href: PROCESS_HREF }];
}

/** Short name for a flow inside a sentence: "Llamadas" / "Reuniones" for the two work-type flows. */
export function flowShortName(
  motion: string | null,
  fallback: string,
  copy: { hosRoleSdr: string; hosRoleAe: string },
): string {
  if (motion === "discovery") return copy.hosRoleSdr;
  if (motion === "closing") return copy.hosRoleAe;
  return fallback;
}
