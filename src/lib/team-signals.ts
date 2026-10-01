/**
 * Inicio's team signals for the Head of Sales (spec R7): at most three, built by rules from
 * /team/adherence and /team/adherence/trend, never written by a model. Rule order decides, then
 * the person's name: people are never ranked against each other by a score.
 * Pure: a signal carries catalog keys and raw params; the component writes the words.
 */
import type { Diagnosis, HosRep } from "./head-of-sales.ts";
import type { TrendPayload, TrendWeek } from "./team-adherence-trend.ts";

export const MAX_SIGNALS = 3;
/** Percentage points of adherence lost, rounded like every "pts" delta on the Team pages. */
export const DROP_POINTS = 15;
/** Scored conversations needed in each window before a drop means anything. */
export const MIN_SCORED = 30;
/** Each window of the drop rule, in weeks of /team/adherence/trend. */
export const WINDOW_WEEKS = 4;

export type SignalTextKey = "signalPlaybook" | "signalPlaybookNoEffect" | "signalCoach" | "signalDrop" | "signalIdle";
export type SignalQuestionKey = `${SignalTextKey}Ask`;

export type TeamSignal = {
  id: string;
  tone: "warn" | "neutral";
  textKey: SignalTextKey;
  params: Record<string, string | number>;
  /** Catalog key of the question the signal puts in the composer, filled with the same params. */
  question: SignalQuestionKey;
};

/** Adherence is a 0-1 share; `scored` counts scored conversations in the window. */
export type SignalRep = {
  userId: string;
  name: string;
  adherence: number | null;
  prevAdherence: number | null;
  scored: number;
  prevScored: number;
  attempts: number;
};

const DIAGNOSIS_TEXT: Partial<Record<Diagnosis["key"], SignalTextKey>> = {
  hosDiagPlaybook: "signalPlaybook",
  hosDiagPlaybookNoEffect: "signalPlaybookNoEffect",
  hosDiagCoach: "signalCoach",
};

function signal(id: string, tone: TeamSignal["tone"], textKey: SignalTextKey, params: TeamSignal["params"]): TeamSignal {
  return { id, tone, textKey, params, question: `${textKey}Ask` };
}

/** Whole points, rounded on the magnitude after snapping float noise ((0.7 - 0.55) * 100 is 14.999...). */
function points(share: number): number {
  const snapped = Math.round(Math.abs(share) * 100 * 1e6) / 1e6;
  return Math.sign(share) * Math.round(snapped);
}

const byName = (a: SignalRep, b: SignalRep) => a.name.localeCompare(b.name, "es");

export function teamSignals(input: { reps: SignalRep[]; diagnosis: Diagnosis[] }): TeamSignal[] {
  const out: TeamSignal[] = [];
  for (const line of input.diagnosis) {
    const textKey = DIAGNOSIS_TEXT[line.key];
    if (textKey) out.push(signal(`diag:${line.key}:${line.motion ?? ""}`, "warn", textKey, { flow: line.motion ?? "" }));
  }
  const reps = [...input.reps].sort(byName);
  for (const rep of reps) {
    if (rep.adherence == null || rep.prevAdherence == null) continue;
    if (rep.scored < MIN_SCORED || rep.prevScored < MIN_SCORED) continue;
    const drop = points(rep.prevAdherence - rep.adherence);
    if (drop < DROP_POINTS) continue;
    out.push(
      signal(`drop:${rep.userId}`, "warn", "signalDrop", {
        name: rep.name,
        points: drop,
        from: points(rep.prevAdherence),
        to: points(rep.adherence),
      }),
    );
  }
  for (const rep of reps) {
    if (rep.attempts === 0) out.push(signal(`idle:${rep.userId}`, "neutral", "signalIdle", { name: rep.name }));
  }
  return out.slice(0, MAX_SIGNALS);
}

function windowOf(weeks: TrendWeek[]) {
  const met = weeks.reduce((sum, week) => sum + week.met_steps, 0);
  const applicable = weeks.reduce((sum, week) => sum + week.applicable_steps, 0);
  return { scored: weeks.reduce((sum, week) => sum + week.scored, 0), adherence: applicable ? met / applicable : null };
}

/**
 * The reps /team/adherence lists (managers already left out), with their attempts and, from the
 * weekly trend, adherence over the last four weeks against the four before (step counts summed,
 * never percentages averaged). No trend (flag off, failed read) leaves adherence unknown.
 */
export function signalReps(reps: Pick<HosRep, "userId" | "name" | "activity">[], trend: TrendPayload | null): SignalRep[] {
  const rows = new Map((trend?.reps ?? []).map((row) => [row.user_id, row.weeks]));
  return reps.map((rep) => {
    const weeks = rows.get(rep.userId) ?? [];
    const current = windowOf(weeks.slice(-WINDOW_WEEKS));
    const previous = windowOf(weeks.slice(-2 * WINDOW_WEEKS, -WINDOW_WEEKS));
    return {
      userId: rep.userId,
      name: rep.name,
      attempts: rep.activity?.attempts ?? 0,
      scored: current.scored,
      prevScored: previous.scored,
      adherence: current.adherence,
      prevAdherence: previous.adherence,
    };
  });
}
