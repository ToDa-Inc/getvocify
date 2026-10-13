// Rep coaching (SDR/AE): pure helpers for /coaching/me/calls (the Coaching tab) and Ask's coaching card. No I/O, no React.
import type { ProductTranslations } from "./product-catalog.ts";

export type CoachFlow = "sdr" | "ae";
export type StepState = "done" | "improvable" | "missing" | "no_evidence" | "not_reached";

export type CoachStepRate = {
  step_id: string;
  label: string;
  rate: number | null;
  prev_rate: number | null;
  peer_median: number | null;
  /** The counts behind the rate (absent from older backends): done includes improvable. */
  done?: number;
  improvable?: number;
  applicable?: number;
};
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

/** GET /coaching/me/calls: the Coaching tab, one interaction type at a time, against the rep's own playbook. */
export type CoachSlip = {
  step_id: string;
  label: string;
  criterion: string | null;
  state: "missing" | "improvable";
  /** What went wrong, to the rep as "tú" (C04 v8; absent on older calls). */
  reason: string | null;
  /** The moment of the call: the rep's words, or where the step should have happened. */
  quote: string | null;
  /** What to try next time, in this call's terms. */
  advice: string | null;
};
export type CoachImproveStep = {
  kind: "step";
  step_id: string;
  label: string;
  criterion: string;
  missing: number;
  improvable: number;
  applicable: number;
  before: { missing: number; improvable: number; applicable: number };
  example: { memo_id: string; observed_at: string; state: string; reason: string | null; quote: string | null; advice: string | null } | null;
  how: string | null;
};
/** The objection left open most: what the prospect said, what the rep replied, the playbook's answer. */
export type CoachImproveObjection = {
  kind: "objection";
  key: string;
  category: string;
  /** The company's own objection's name; null for a fixed category. */
  label: string | null;
  open: number;
  total: number;
  example: { memo_id: string; observed_at: string; quote: string | null; response: string | null } | null;
  how: string | null;
};
export type CoachImprove = CoachImproveStep | CoachImproveObjection;
/** "Tus pasos": a step over the last weeks, with its rate before only when enough calls back it. */
export type CoachStepBoardItem = {
  step_id: string;
  label: string;
  done: number;
  improvable: number;
  missing: number;
  applicable: number;
  rate: number | null;
  prev_rate: number | null;
};
export type CoachCall = {
  memo_id: string;
  observed_at: string | null;
  duration_s: number | null;
  summary_line: string;
  meeting_agreed: boolean;
  done: number;
  applicable: number;
  /** Empty when there was nothing to improve in this call. */
  slips: CoachSlip[];
};
export type CoachCalls = {
  types: { key: string; label: string | null; conversations: number }[];
  type: string | null;
  window_weeks: number;
  conversations: number;
  improve: CoachImprove[];
  steps: CoachStepBoardItem[];
  calls: CoachCall[];
};

type Product = ProductTranslations;
export type CoachKey = Extract<keyof Product, `coach${string}`>;
export type CoachTone = "success" | "warning" | "muted";

export const STATE_VIEW: Record<StepState, { glyph: string; labelKey: CoachKey; tone: CoachTone; counted: boolean }> = {
  done: { glyph: "✅", labelKey: "coachStateDone", tone: "success", counted: true },
  improvable: { glyph: "🟡", labelKey: "coachStateImprovable", tone: "warning", counted: true },
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

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

export function focusTitle(p: Product, focus: Pick<CoachFocus, "label">): string {
  return fill(p.coachFocusTitle, { label: focus.label });
}

export function weekTotalLine(p: Product, total: CoachFocus["week_total"]): string {
  return fill(p.coachFocusWeekTotal, { done: total.done, applicable: total.applicable });
}

/** All, none or some done: the only three tones a count gets, so no threshold is invented. */
export function countTone(done: number, total: number): "success" | "warning" | "destructive" | "muted" {
  if (!total) return "muted";
  return done === total ? "success" : done === 0 ? "destructive" : "warning";
}

/** The extraction sometimes leaves markdown in the summary ("Resultado:** …"). */
export function cleanSummaryLine(line: string | null | undefined): string {
  return String(line ?? "").replace(/^\s*\**\s*Resultado:\s*\**\s*/i, "").replace(/\*\*/g, "").trim();
}

export function durationLabel(p: Product, seconds: number | null | undefined): string | null {
  if (!seconds || seconds <= 0) return null;
  return fill(p.coachDuration, { min: Math.max(1, Math.round(seconds / 60)) });
}

export function peerMedianLabel(p: Product, median: number | null | undefined): string | null {
  if (median === null || median === undefined) return null;
  return fill(p.coachPeerMedian, { value: formatPercent(median) });
}

/** Below this many calls where a step applied, a rate says nothing ("0 %" of one call): show the count. */
export const MIN_CALLS_FOR_RATE = 3;

/** "83 %" with enough calls behind it, "1 de 2" with fewer, "—" with none. */
export function boardValue(p: Product, step: Pick<CoachStepBoardItem, "done" | "applicable" | "rate">): string {
  if (!step.applicable) return "—";
  if (step.applicable < MIN_CALLS_FOR_RATE) return fill(p.coachStepCount, { done: step.done, applicable: step.applicable });
  return formatPercent(step.rate);
}

/** The arrow against the weeks before, only when both sides rest on enough calls. */
export function boardTrend(step: Pick<CoachStepBoardItem, "applicable" | "rate" | "prev_rate">): Trend {
  return step.applicable >= MIN_CALLS_FOR_RATE ? trendOf(step.rate, step.prev_rate) : null;
}

