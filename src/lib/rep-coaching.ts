// Rep coaching (SDR/AE): pure helpers for the four /coaching/* responses. No I/O, no React.
import type { ProductTranslations } from "./product-catalog.ts";

export type CoachFlow = "sdr" | "ae";
export type StepState = "done" | "missing" | "no_evidence" | "not_reached";

export type CoachStepRate = { step_id: string; label: string; rate: number | null; prev_rate: number | null; peer_median: number | null };
export type CoachNumbers = { conversations: number; meetings_agreed: number; process_complete: number; interactions: number };
export type CoachFocus = {
  step_id: string;
  label: string;
  criterion: string;
  example: string;
  why: { rate: number | null; applicable: number; missing: number; peer_median: number | null };
  progress: { date: string; done: number; applicable: number }[];
  week_total: { done: number; applicable: number; rate: number | null };
  achieved: boolean;
};
export type CoachConversion = { complete_rate: number | null; incomplete_rate: number | null; complete_n: number; incomplete_n: number };
export type CoachSummary = {
  flow: CoachFlow;
  available_flows?: CoachFlow[];
  motion: string;
  week_start: string;
  steps: CoachStepRate[];
  numbers: CoachNumbers;
  prev_numbers: CoachNumbers;
  focus: CoachFocus | null;
  conversion: CoachConversion | null;
  playbook_published: boolean;
};
export type CoachInteractionStep = { step_id: string; label: string; state: StepState; quote: string | null };
export type CoachInteraction = {
  memo_id: string;
  user_id: string;
  observed_at: string | null;
  motion: string;
  is_conversation: boolean;
  meeting_agreed: boolean;
  duration_s: number | null;
  summary_line: string;
  steps: CoachInteractionStep[];
};
export type CoachInteractions = { items: CoachInteraction[] };
export type CoachProcess = {
  weeks: string[];
  steps: { step_id: string; label: string; by_week: { done: number; applicable: number; rate: number | null }[]; rate: number | null; peer_median: number | null }[];
  objections: { category: string; total: number; resolved: number; open: number }[];
};
export type CoachExamples = {
  steps: { step_id: string; label: string; criterion: string; example: string; moments: { quote: string }[] }[];
  objections: { category: string; guidance: string; best_response: string }[];
};

type Product = ProductTranslations;
export type CoachKey = Extract<keyof Product, `coach${string}`>;
export type CoachTone = "success" | "warning" | "muted";

export const STEP_STATES: StepState[] = ["done", "missing", "no_evidence", "not_reached"];

export const STATE_VIEW: Record<StepState, { glyph: string; labelKey: CoachKey; tone: CoachTone; counted: boolean }> = {
  done: { glyph: "✅", labelKey: "coachStateDone", tone: "success", counted: true },
  missing: { glyph: "❌", labelKey: "coachStateMissing", tone: "warning", counted: true },
  no_evidence: { glyph: "❔", labelKey: "coachStateNoEvidence", tone: "muted", counted: false },
  not_reached: { glyph: "⚪", labelKey: "coachStateNotReached", tone: "muted", counted: false },
};

export function stateView(state: string) {
  return STATE_VIEW[state as StepState] ?? STATE_VIEW.no_evidence;
}

/** 0..1 -> "63 %"; null (no data) is "—", never 0. */
export function formatPercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)} %`;
}

export const TREND_DEAD_BAND = 0.05;

export type Trend = "up" | "down" | "flat" | null;

/** Arrow vs last week with a 5-point dead band; null when either side has no data. */
export function trendOf(rate: number | null, prev: number | null): Trend {
  if (rate === null || prev === null) return null;
  const diff = rate - prev;
  if (diff > TREND_DEAD_BAND + 1e-9) return "up";
  if (diff < -(TREND_DEAD_BAND + 1e-9)) return "down";
  return "flat";
}

export function trendArrow(trend: Trend): string {
  return trend === "up" ? "↑" : trend === "down" ? "↓" : trend === "flat" ? "→" : "";
}

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

export function focusTitle(p: Product, focus: Pick<CoachFocus, "label">): string {
  return fill(p.coachFocusTitle, { label: focus.label });
}

export function focusWhy(p: Product, why: CoachFocus["why"]): string {
  return fill(p.coachFocusWhy, { missing: why.missing, applicable: why.applicable });
}

export function weekTotalLine(p: Product, total: CoachFocus["week_total"]): string {
  return fill(p.coachFocusWeekTotal, { done: total.done, applicable: total.applicable });
}

/** Only when the backend sent a conversion split (it hides it below the minimum sample). */
export function conversionSentence(
  p: Product,
  conversion: CoachConversion | null | undefined,
  flow: CoachFlow | null | undefined = "sdr",
): string | null {
  if (!conversion) return null;
  return fill(flow === "ae" ? p.coachConversionAe : p.coachConversion, {
    complete: formatPercent(conversion.complete_rate),
    incomplete: formatPercent(conversion.incomplete_rate),
    completeN: conversion.complete_n,
    incompleteN: conversion.incomplete_n,
  });
}

/** "steps done: X of Y": only done + missing count; unknown and not-reached never penalise. */
export function stepsDone(steps: { state: string }[]): { done: number; total: number } {
  let done = 0;
  let total = 0;
  for (const step of steps) {
    if (step.state === "done") {
      done += 1;
      total += 1;
    } else if (step.state === "missing") total += 1;
  }
  return { done, total };
}

export function stepsDoneLine(p: Product, steps: { state: string }[]): string | null {
  const { done, total } = stepsDone(steps);
  return total === 0 ? null : fill(p.coachStepsDone, { done, total });
}

export function durationLabel(p: Product, seconds: number | null | undefined): string | null {
  if (!seconds || seconds <= 0) return null;
  return fill(p.coachDuration, { min: Math.max(1, Math.round(seconds / 60)) });
}

export function interactionsTabKey(flow: CoachFlow | null | undefined): CoachKey {
  return flow === "ae" ? "coachTabMeetings" : "coachTabCalls";
}

/** The AE goal is the next meeting; the SDR one is the meeting agreed on the call. */
export function meetingsTileKey(flow: CoachFlow | null | undefined): CoachKey {
  return flow === "ae" ? "coachNumMeetingsAe" : "coachNumMeetings";
}

/** Only a general rep (role null/general) picks a flow, and only when both have a published playbook. */
export function isGeneralRep(salesRole: string | null | undefined): boolean {
  return salesRole === null || salesRole === undefined || salesRole === "general";
}

export function canPickFlow(salesRole: string | null | undefined, available: CoachFlow[] | null | undefined): boolean {
  return isGeneralRep(salesRole) && !!available && available.includes("sdr") && available.includes("ae");
}

/** The muted "viewing" line: general reps with a single published flow. */
export function viewingFlowKey(
  salesRole: string | null | undefined,
  available: CoachFlow[] | null | undefined,
  flow: CoachFlow | null | undefined,
): CoachKey | null {
  if (!isGeneralRep(salesRole) || canPickFlow(salesRole, available) || !flow) return null;
  return flow === "ae" ? "coachViewingMeetings" : "coachViewingCalls";
}

/** Newest self report from the bell's notifications; null when there is none. */
export function latestSelfReportId(items: { report_id: string; scope: string; period_start: string }[] | null | undefined): string | null {
  const own = (items ?? []).filter((item) => item.scope === "self");
  if (own.length === 0) return null;
  own.sort((a, b) => (a.period_start < b.period_start ? 1 : a.period_start > b.period_start ? -1 : 0));
  return own[0].report_id;
}

export function peerMedianLabel(p: Product, median: number | null | undefined): string | null {
  if (median === null || median === undefined) return null;
  return fill(p.coachPeerMedian, { value: formatPercent(median) });
}

export function hasAnyPeer(steps: { peer_median: number | null }[]): boolean {
  return steps.some((step) => step.peer_median !== null && step.peer_median !== undefined);
}

export function numberVsLast(p: Product, previous: number): string {
  return fill(p.coachVsLast, { value: previous });
}

export type InteractionFilters = { stepId: string; state: string; meetingOnly: boolean };

export function interactionsQuery(filters: InteractionFilters, flow?: CoachFlow | null): string {
  const params = new URLSearchParams();
  if (filters.stepId) params.set("step_id", filters.stepId);
  if (filters.state) params.set("state", filters.state);
  if (filters.meetingOnly) params.set("meeting", "true");
  params.set("limit", "50");
  if (flow) params.set("flow", flow);
  return params.toString();
}

export function objectionCountsLine(p: Product, o: { resolved: number; open: number }): string {
  return fill(p.coachObjectionCounts, { resolved: o.resolved, open: o.open });
}

