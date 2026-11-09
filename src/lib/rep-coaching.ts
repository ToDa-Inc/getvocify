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
/** What a prospect objected to in one call, with the key the playbook answers it by. */
export type CoachCallObjection = {
  key: string;
  category: string;
  label: string | null;
  how: string | null;
  resolution: "open" | "resolved" | "unknown";
  quote: string | null;
  response: string | null;
  /** C04 v9: what it really was (no need, another tool, the idea itself...); absent on older calls. */
  nature?: CoachObjectionNature | null;
  /** C04 v9: what the reply did and what would have served better. */
  advice?: string | null;
  /** C04 v9: what the rep could have said, written with the whole call read. */
  line?: string | null;
};
export type CoachObjectionNature = "sin_dolor" | "alternativa" | "fondo" | "objecion" | "duda";
/** C04 v9: the call as a whole, shown before its objections and steps. Absent on calls read before it. */
export type CoachCallReading = {
  verdict: string | null;
  pain: "found" | "absent" | "not_reached" | "unclear" | null;
  decisive_moment: { quote: string; meaning: string | null } | null;
  root_cause: string | null;
  /** The one thing that cost the call most. */
  main_error: string | null;
  /** What to say at the decisive moment next time, and then by the prospect's likely answer. */
  steer: { line: string | null; branches: { if: string; then: string }[] } | null;
  /** The realistic best this call could have given, and whether the rep got it. */
  best_outcome: { what: string | null; got: boolean | null } | null;
};
export type CoachCall = {
  memo_id: string;
  observed_at: string | null;
  duration_s: number | null;
  summary_line: string;
  meeting_agreed: boolean;
  /** call / meeting / visit, as the interaction was captured (absent from an older backend). */
  kind?: string | null;
  done: number;
  applicable: number;
  /** Empty when there was nothing to improve in this call. */
  slips: CoachSlip[];
  /** Absent from a backend older than the objections of a call. */
  objections?: CoachCallObjection[];
  reading?: CoachCallReading | null;
};
/** Every step the rep slipped on, with the calls it slipped in (newest first). */
export type CoachSlippedStep = {
  step_id: string;
  label: string;
  criterion: string;
  missing: number;
  improvable: number;
  applicable: number;
  /** The playbook's own example phrase for the step. */
  example: string | null;
  occurrences: { memo_id: string; observed_at: string; state: "missing" | "improvable" | "done"; reason: string | null; quote: string | null; advice: string | null }[];
};
/** Every objection the prospects raised, how each went and the playbook's answer. */
export type CoachObjectionBreakdown = {
  key: string;
  category: string;
  label: string | null;
  how: string | null;
  total: number;
  open: number;
  resolved: number;
  occurrences: { memo_id: string; observed_at: string; resolution: "open" | "resolved" | "unknown"; quote: string | null; response: string | null }[];
};
export type CoachCalls = {
  types: { key: string; label: string | null; conversations: number }[];
  type: string | null;
  window_weeks: number;
  conversations: number;
  /** Absent from a backend older than the "En qué mejorar" tables. */
  slipped_steps?: CoachSlippedStep[];
  objections?: CoachObjectionBreakdown[];
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

/** The window's calls at a glance, from what GET /coaching/me/calls already sends: how many conversations
 * (and of which channel), the share of the process done (the backend's own count: done over done + not
 * done, so it matches every other surface), how that compares with the weeks before, and meetings agreed. */
export type CoachSummary = {
  conversations: number;
  byKind: Record<string, number>;
  rate: number | null;
  /** The last two weeks against the two before them; null while either side has fewer than MIN_CALLS_FOR_RATE calls. */
  recent: { rate: number; prev: number } | null;
  meetings: number;
};

const TWO_WEEKS_MS = 14 * 24 * 3600 * 1000;

export function summarizeCalls(
  calls: Pick<CoachCall, "observed_at" | "kind" | "done" | "applicable" | "meeting_agreed">[],
  now: number = Date.now(),
): CoachSummary {
  const byKind: Record<string, number> = {};
  let done = 0;
  let applicable = 0;
  const sides = { recent: { done: 0, applicable: 0, calls: 0 }, prev: { done: 0, applicable: 0, calls: 0 } };
  for (const call of calls) {
    const kind = call.kind || "call";
    byKind[kind] = (byKind[kind] ?? 0) + 1;
    if (!call.applicable) continue;
    done += call.done;
    applicable += call.applicable;
    const age = now - new Date(call.observed_at ?? "").getTime();
    const side = age >= 0 && age < TWO_WEEKS_MS ? sides.recent : age >= TWO_WEEKS_MS && age < 2 * TWO_WEEKS_MS ? sides.prev : null;
    if (side) {
      side.done += call.done;
      side.applicable += call.applicable;
      side.calls += 1;
    }
  }
  const enough = sides.recent.calls >= MIN_CALLS_FOR_RATE && sides.prev.calls >= MIN_CALLS_FOR_RATE;
  return {
    conversations: calls.length,
    byKind,
    rate: applicable ? done / applicable : null,
    recent: enough ? { rate: sides.recent.done / sides.recent.applicable, prev: sides.prev.done / sides.prev.applicable } : null,
    meetings: calls.filter((call) => call.meeting_agreed).length,
  };
}

/** How many moments a pager shows: the newest `cap` until the person asks for the earlier ones. */
export function visibleMomentCount(total: number, expanded: boolean, cap = 5): number {
  return expanded || total <= cap ? total : cap;
}

/** The objections the table lists: the catch-all "Otra" is left out (the summary totals still count it). */
export function tableObjections(objections: CoachObjectionBreakdown[]): CoachObjectionBreakdown[] {
  return objections.filter((objection) => objection.category !== "other");
}

/** The empty text of the objections table: nothing given at all, or only the untyped ones it leaves out. */
export function noObjectionsKey(given: number, listed: number): "coachNoObjections" | "coachOnlyUntyped" {
  return given > 0 && listed === 0 ? "coachOnlyUntyped" : "coachNoObjections";
}

/** The pager's "show earlier" action: a singular wording when exactly one moment is left. */
export function earlierKey(count: number): "coachShowEarlier" | "coachShowEarlierOne" {
  return count === 1 ? "coachShowEarlierOne" : "coachShowEarlier";
}
