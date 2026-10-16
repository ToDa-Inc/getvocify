/**
 * Pure helpers of the playbook assistant screens (guided questions, trial, improvements): which view the URL asks
 * for, how a rate is written, what a document gave, and the little texts the screens build. No React, no I/O.
 */

export type ImproveView = "assistant" | "trial" | "improve";
const VIEWS: readonly ImproveView[] = ["assistant", "trial", "improve"];

/** The view `?view=` asks for, or null (the playbook as always). */
export function viewFromParams(params: URLSearchParams): ImproveView | null {
  const value = params.get("view");
  return VIEWS.find((view) => view === value) ?? null;
}

export type RateLabel = { kind: "rate" | "count"; text: string };

/**
 * "75%" from `min` cases on, the plain count ("2 de 2") below: a percentage of two calls says nothing and looks
 * like a result. `of` is the word between the numbers in the screen's language.
 */
export function rateLabel(good: number, total: number, options: { min?: number; of?: string } = {}): RateLabel {
  const { min = 3, of = "de" } = options;
  if (total >= min && total > 0) return { kind: "rate", text: `${Math.round((good / total) * 100)}%` };
  return { kind: "count", text: `${good} ${of} ${total}` };
}

type EditorLike = { steps?: unknown[]; objections?: { category: string }[] };
export type IntakeLike = {
  fallback?: boolean;
  types: { sales_motion_key: string; editor: EditorLike }[];
  company?: { knowledge?: { proofs?: unknown[] } } | null;
};
export type IntakeSummary = { types: number; steps: number; objections: number; questions: number; proofs: number };

/**
 * What one or several documents left in the playbook, for the "he entendido…" line. A call type seen in two
 * results counts once, with what its latest version holds; a result that could not be read adds nothing.
 * `objections` are the answers to the usual objections, `questions` the team's own ones (product questions).
 */
export function intakeSummary(results: IntakeLike[]): IntakeSummary {
  const byType = new Map<string, EditorLike>();
  let proofs = 0;
  for (const result of results) {
    if (result.fallback) continue;
    for (const type of result.types) byType.set(type.sales_motion_key, type.editor);
    if (result.company) proofs = result.company.knowledge?.proofs?.length ?? 0;
  }
  const summary: IntakeSummary = { types: byType.size, steps: 0, objections: 0, questions: 0, proofs };
  for (const editor of byType.values()) {
    summary.steps += editor.steps?.length ?? 0;
    for (const objection of editor.objections ?? []) {
      if (objection.category === "custom") summary.questions += 1;
      else summary.objections += 1;
    }
  }
  return summary;
}

/** "Integración con Salesforce: Sí, con Salesforce y HubSpot." in at most `max` characters. */
export function savedLine(label: string, answer: string, max = 90): string {
  const text = label.trim() ? `${label.trim()}: ${answer.trim()}` : answer.trim();
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

/** "3 de 10": the question on screen, never past the total. */
export function progressText(session: { answered: number; skipped: number; total: number }, of: string): string {
  const position = Math.min(session.answered + session.skipped + 1, Math.max(session.total, 1));
  return `${position} ${of} ${session.total}`;
}

export type TrialMark = "approved" | "corrected" | "unknown" | "pending";

/** One segment per case of the trial: what the Head of Sales decided for it, then the ones still to see. */
export function trialMeter(verdicts: string[], total: number): TrialMark[] {
  const marks = verdicts.map((verdict): TrialMark => {
    if (verdict === "approve") return "approved";
    if (verdict === "unknown") return "unknown";
    return "corrected";
  });
  while (marks.length < total) marks.push("pending");
  return marks;
}

export type SplitQuestion = { lead: string; quote: string | null; ask: string };

/**
 * "Un cliente dijo «…» ¿Qué respondéis?" as the three things the screen shows apart: what introduces it, the customer's
 * words as a quote, and the question. A sentence without the customer's words stays whole in `ask`.
 */
export function splitQuestion(question: string, example: string | null): SplitQuestion {
  if (example) {
    for (const [open, close] of [["«", "»"], ["“", "”"]] as const) {
      const wrapped = `${open}${example}${close}`;
      const at = question.indexOf(wrapped);
      if (at >= 0) return { lead: question.slice(0, at).trim(), quote: example, ask: question.slice(at + wrapped.length).trim() };
    }
  }
  return { lead: "", quote: null, ask: question };
}

export type TopicNames = { kinds: Record<string, string>; question: string; none: string; unknown: string };

/** What the trial's weak topics are called: a usual kind by its name, the rest as the team's own objection is named. */
export function topicLabel(topic: string, names: TopicNames): string {
  if (!topic) return names.unknown;
  if (topic === "question") return names.question;
  if (topic === "none") return names.none;
  if (topic === "unknown") return names.unknown;
  return names.kinds[topic] ?? topic;
}

export type QueueTone = "success" | "warning" | "muted" | "pending";
const MARK_TONE: Record<string, QueueTone> = { success: "success", failed: "warning", unused: "muted" };

/** One segment per judged card of an answer, the latest `max`: green it was said and settled it, amber it was said and did not, grey it was not said, pale unknown. */
export function queueMeter(marks: string[], max = 12): QueueTone[] {
  return marks.slice(-max).map((mark) => MARK_TONE[mark] ?? "pending");
}

/** The verdicts the Head of Sales can set on a card, i.e. the ones that differ from what the judge decided. A suggestion nobody said has nothing to correct. */
export function verdictChoices(mark: string): ("resolved" | "not_resolved")[] {
  if (mark === "success") return ["not_resolved"];
  if (mark === "failed") return ["resolved"];
  if (mark === "unknown") return ["resolved", "not_resolved"];
  return [];
}

/** The big figure of a stat: "78%" from three cases, "2 de 2" below, a dash when there is nothing to count. */
export function statFigure(good: number, total: number, of: string): string {
  return total > 0 ? rateLabel(good, total, { of }).text : "—";
}
