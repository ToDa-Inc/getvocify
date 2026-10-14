// Equipo (Head of Sales): pure helpers for GET /team/coaching. No I/O, no React.
import type { ProductTranslations } from "./product-catalog.ts";
import { fill, formatPercent, MIN_CALLS_FOR_RATE } from "./rep-coaching.ts";

type Product = ProductTranslations;

export type TeamStepCell = { done: number; applicable: number; rate: number | null };
export type TeamRep = {
  user_id: string;
  name: string;
  adherence: number | null;
  conversations: number;
  meetings: number;
  steps: Record<string, TeamStepCell>;
};
export type TeamSide = { calls: number; goals: number; rate: number | null };
export type TeamVerdict = "helps" | "hurts" | "no_difference" | "few_data";
export type TeamEffect = { with: TeamSide; without: TeamSide; verdict: TeamVerdict };
export type TeamLossCause = {
  cause: string;
  /** The company's own objection's name; null otherwise. */
  label: string | null;
  count: number;
  share: number | null;
  examples: { memo_id: string; quote: string; rep: string; observed_at: string; from_history: boolean }[];
};
export type TeamCoaching = {
  period: string;
  types: { key: string; label: string | null; conversations: number }[];
  type: string | null;
  goal: "meeting_booked";
  follow: {
    adherence: number | null;
    prev_adherence: number | null;
    conversations: number;
    steps: ({ step_id: string; label: string } & TeamStepCell)[];
    reps: TeamRep[];
  };
  works: { process: TeamEffect | null; steps: ({ step_id: string; label: string } & TeamEffect)[] };
  losses: {
    total: number;
    by_source: { not_interested: number; disqualified: number; crm_lost: number };
    causes: TeamLossCause[];
  };
};

/** A goal needs this many marked meetings before any comparison says something (team_coaching.MIN_GOALS). */
export const MIN_GOALS = 3;

export type HeatTone = "none" | "few" | "low" | "mid" | "high";

/** A cell's colour: none without calls, few under three, then low / mid / high at 50 % and 80 %. */
export function heatTone(cell: Pick<TeamStepCell, "applicable" | "rate">): HeatTone {
  if (!cell.applicable || cell.rate === null) return "none";
  if (cell.applicable < MIN_CALLS_FOR_RATE) return "few";
  if (cell.rate >= 0.8) return "high";
  if (cell.rate >= 0.5) return "mid";
  return "low";
}

/** "83 %" with enough calls, "1/2" with fewer, "—" with none: never a % of one call. */
export function cellValue(cell: Pick<TeamStepCell, "done" | "applicable" | "rate">): string {
  if (!cell.applicable) return "—";
  if (cell.applicable < MIN_CALLS_FOR_RATE) return `${cell.done}/${cell.applicable}`;
  return formatPercent(cell.rate);
}

/** Meetings marked so far across the comparison: the whole process splits every conversation. */
export function goalsMarked(works: TeamCoaching["works"]): number {
  const process = works.process;
  return process ? process.with.goals + process.without.goals : 0;
}

/** Whether "¿Funciona el playbook?" has anything to show beyond "not enough outcomes yet". */
export function worksHasVerdict(works: TeamCoaching["works"]): boolean {
  return [works.process, ...works.steps].some((effect) => effect && effect.verdict !== "few_data");
}

const OBJECTION_PREFIX = "obstacle:";

/** A loss cause as the Head of Sales reads it: the company's objection by its name, a fixed objection
 * by its category, an obstacle, "never got to talk" or "no clear cause in the call". */
export function causeLabel(p: Product, cause: Pick<TeamLossCause, "cause" | "label">): string {
  if (cause.label) return cause.label;
  if (cause.cause === "no_conversation") return p.teamCauseNoConversation;
  if (cause.cause === "unclear") return p.teamCauseUnclear;
  if (cause.cause.startsWith(OBJECTION_PREFIX)) {
    const key = cause.cause.slice(OBJECTION_PREFIX.length) as keyof typeof p.teamCauseObstacles;
    return p.teamCauseObstacles[key] ?? p.teamCauseObstacles.other;
  }
  const key = cause.cause as keyof typeof p.playbookObjectionCategories;
  return p.playbookObjectionCategories[key] ?? cause.cause;
}

/** "12 perdidas · 7 no interesado · 3 no cualificado · 2 perdidas en el CRM", without the zeros. */
export function lossesLine(p: Product, losses: TeamCoaching["losses"]): string {
  const parts = [fill(p.teamLossesTotal, { count: losses.total })];
  if (losses.by_source.not_interested) parts.push(fill(p.teamLossesNotInterested, { count: losses.by_source.not_interested }));
  if (losses.by_source.disqualified) parts.push(fill(p.teamLossesDisqualified, { count: losses.by_source.disqualified }));
  if (losses.by_source.crm_lost) parts.push(fill(p.teamLossesCrm, { count: losses.by_source.crm_lost }));
  return parts.join(" · ");
}
