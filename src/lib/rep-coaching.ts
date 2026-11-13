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
  /** C04 v10: what happened right after the rep's reply, and the prospect's words that show it; absent on older calls. */
  after?: CoachAfter | null;
  after_quote?: string | null;
  quote: string | null;
  response: string | null;
  /** C04 v11 (2026-11-13): what each quote meant, in clean words; the quote stays as the proof. Absent on older calls. */
  said?: string | null;
  response_said?: string | null;
  after_said?: string | null;
  /** C04 v9: what it really was (no need, another tool, the idea itself...); absent on older calls. */
  nature?: CoachObjectionNature | null;
  /** C04 v9: what the reply did and what would have served better. */
  advice?: string | null;
  /** C04 v9: what the rep could have said, written with the whole call read. */
  line?: string | null;
};
export type CoachObjectionNature = "sin_dolor" | "alternativa" | "fondo" | "objecion" | "duda";
/** C04 v10: what happened right after the rep's reply to an objection, a fact of the call. */
export type CoachAfter = "advanced" | "stalled" | "ended" | "unknown";
/** An objection the company has no playbook answer for yet (read with C04 v10). */
export const UNANSWERED_KEY = "unanswered";
/** C04 v9: the call as a whole, shown before its objections and steps. Absent on calls read before it. */
export type CoachCallReading = {
  verdict: string | null;
  pain: "found" | "absent" | "not_reached" | "unclear" | null;
  decisive_moment: { quote: string; said?: string | null; meaning: string | null } | null;
  root_cause: string | null;
  /** The one thing that cost the call most. */
  main_error: string | null;
  /** What to say at the decisive moment next time, and then by the prospect's likely answer. */
  steer: { line: string | null; branches: { if: string; then: string }[] } | null;
  /** The realistic best this call could have given, and whether the rep got it. */
  best_outcome: { what: string | null; got: boolean | null } | null;
};
/** C04 findings as the rep's Coaching shows them: each with what to do next time. Absent on calls read before them.
 * Each `*_said` (findings v3) is what that quote meant in clean words; absent on calls read before it. */
export type CoachCallFindings = {
  /** Questions not fully answered; `better` is what to answer next time, none when the company has no answer yet. */
  questions: { topic: string; quote: string; said?: string | null; answered: "yes" | "partly" | "later" | "no"; answer: string | null; answer_said?: string | null; better: string | null; no_answer: boolean }[];
  /** Doors the prospect opened that the rep let pass, with what the rep said right after and the line to try. */
  signals: { topic: string; quote: string; said?: string | null; kind: string; reply: string | null; reply_said?: string | null; why: string; line: string | null }[];
  /** What the rep said that moved the call on and the playbook does not have, and when to use it again. */
  worked: { topic: string; quote: string; said?: string | null; after_quote: string; after_said?: string | null; why: string; use_when: string | null }[];
  /** Objections none of the playbook's answers is for: what they said, the reply, what followed, what to say instead. */
  new_objections?: { topic: string; quote: string; said?: string | null; reply: string | null; reply_said?: string | null; after: CoachAfter; better: string | null }[];
  /** What the rep gave or relaxed, against what the company's material says is normal. Equipo's panel only. */
  concessions?: { kind: string | null; what: string; normal: string | null; quote: string; said?: string | null }[];
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
  findings?: CoachCallFindings | null;
};

/** Whether a call's findings give the rep anything to open. */
export function hasFindings(findings: CoachCallFindings | null | undefined): boolean {
  return Boolean(findings && (findings.questions.length || findings.signals.length || findings.worked.length || findings.concessions?.length || findings.new_objections?.length));
}
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
  /** C04 v10: how many times the call moved on, stalled or ended right after the reply. Absent from an older backend. */
  /** True when the table counts only calls read against every answer, by what followed each reply. */
  by_after?: boolean;
  advanced?: number;
  stalled?: number;
  ended?: number;
  occurrences: { memo_id: string; observed_at: string; resolution: "open" | "resolved" | "unknown"; after?: CoachAfter | null; after_quote?: string | null; quote: string | null; response: string | null; said?: string | null; response_said?: string | null; after_said?: string | null }[];
  /** What colleagues replied to this objection when the call moved on (only for a rep who may read the team's calls). */
  worked?: { quote: string | null; response: string | null; after_quote: string | null; said?: string | null; response_said?: string | null; after_said?: string | null }[];
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

/** Whether a row is read by what followed each reply (C04 v10) rather than by whether the prospect gave in. */
export function readByAfter(objection: Pick<CoachObjectionBreakdown, "advanced" | "stalled" | "ended" | "by_after">): boolean {
  if (objection.by_after !== undefined) return objection.by_after;
  return (objection.advanced ?? 0) + (objection.stalled ?? 0) + (objection.ended ?? 0) > 0;
}

/** A moment's tone from what followed the reply: moved on green, stalled amber, ended red; without it, as resolved. */
export function afterTone(after: CoachAfter | null | undefined, resolution: "open" | "resolved" | "unknown"): "good" | "half" | "bad" | "unknown" {
  if (after === "advanced") return "good";
  if (after === "stalled") return "half";
  if (after === "ended") return "bad";
  if (after === "unknown") return "unknown";
  return resolution === "resolved" ? "good" : resolution === "open" ? "bad" : "unknown";
}

/** The empty text of the objections table: nothing given at all, or only the untyped ones it leaves out. */
export function noObjectionsKey(given: number, listed: number): "coachNoObjections" | "coachOnlyUntyped" {
  return given > 0 && listed === 0 ? "coachOnlyUntyped" : "coachNoObjections";
}

/** The pager's "show earlier" action: a singular wording when exactly one moment is left. */
export function earlierKey(count: number): "coachShowEarlier" | "coachShowEarlierOne" {
  return count === 1 ? "coachShowEarlierOne" : "coachShowEarlier";
}

/** One row of Coaching's tables (and Equipo's): how many of the times it came up went well, half way, unclear or badly. */
export type TableRow = {
  id: string;
  title: string;
  good: number;
  half: number;
  unknown: number;
  bad: number;
  /** How many times in all; absent for a plain count (then the row shows `good` alone, with no bar). */
  of?: number;
  /** A group rather than one item: lighter. */
  group?: boolean;
  /** One short line under the title: who, or a tag. */
  note?: string;
};

/** The objections as table rows: by what followed each reply (C04 v10) once any has it, else resolved or not. */
export function objectionTable(objections: CoachObjectionBreakdown[], unansweredTitle: string, categories: Record<string, string>) {
  const listed = tableObjections(objections);
  const byAfter = listed.some(readByAfter);
  const rows: TableRow[] = listed.map((objection) => {
    const group = objection.key === UNANSWERED_KEY;
    const title = group ? unansweredTitle : objection.label || categories[objection.category] || objection.category;
    if (byAfter) {
      const advanced = objection.advanced ?? 0, stalled = objection.stalled ?? 0, ended = objection.ended ?? 0;
      return { id: objection.key, title, group, good: advanced, half: stalled, unknown: Math.max(0, objection.total - advanced - stalled - ended), bad: ended, of: objection.total };
    }
    return {
      id: objection.key,
      title,
      group,
      good: objection.resolved,
      half: 0,
      unknown: Math.max(0, objection.total - objection.open - objection.resolved),
      bad: objection.open,
      of: objection.total,
    };
  });
  return { listed, byAfter, rows };
}
