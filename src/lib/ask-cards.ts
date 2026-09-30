import type { CoachConversion, CoachFlow, CoachFocus, CoachStepRate } from "./rep-coaching.ts";
import type { ProcessHealthFlow } from "./head-of-sales.ts";

/**
 * What the Coach and Team screens show, handed over by the same producer when Ask read it this turn.
 * The server builds a card from a tool result; the model's text never does.
 */
export type AskCoachingCard = {
  kind: "coaching";
  flow: CoachFlow | null;
  focus: CoachFocus | null;
  steps: CoachStepRate[];
  conversion: CoachConversion | null;
};

export type AskTeamRep = { user_id?: string | null; name: string; focus: { label: string; rate: number | null } | null };
export type AskTeamCard = {
  kind: "team";
  period: string;
  one_rep: boolean;
  adherence: number | null;
  previous: number | null;
  process: ProcessHealthFlow[];
  reps: AskTeamRep[];
  more_reps: number;
};

export type AskCard = AskCoachingCard | AskTeamCard;

const MAX_STEPS = 8;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function rate(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : null;
}

function coaching(raw: Record<string, unknown>): AskCoachingCard | null {
  const steps = (Array.isArray(raw.steps) ? raw.steps : [])
    .filter((s): s is CoachStepRate => isRecord(s) && typeof s.label === "string" && s.label.trim() !== "")
    .slice(0, MAX_STEPS)
    .map((s) => ({ ...s, rate: rate(s.rate), prev_rate: rate(s.prev_rate), peer_median: rate(s.peer_median) }));
  const focus = isRecord(raw.focus) && typeof raw.focus.label === "string" ? (raw.focus as CoachFocus) : null;
  if (!focus && steps.length === 0) return null;
  return {
    kind: "coaching",
    flow: raw.flow === "ae" || raw.flow === "sdr" ? raw.flow : null,
    focus,
    steps,
    conversion: isRecord(raw.conversion) ? (raw.conversion as CoachConversion) : null,
  };
}

function team(raw: Record<string, unknown>): AskTeamCard | null {
  const process = (Array.isArray(raw.process) ? raw.process : []).filter(
    (f): f is ProcessHealthFlow => isRecord(f) && typeof f.motion === "string" && typeof f.verdict === "string",
  );
  const reps = (Array.isArray(raw.reps) ? raw.reps : []).filter(
    (r): r is AskTeamRep => isRecord(r) && typeof r.name === "string" && r.name.trim() !== "",
  );
  const adherence = rate(raw.adherence);
  if (adherence === null && process.length === 0 && reps.length === 0) return null;
  return {
    kind: "team",
    period: typeof raw.period === "string" ? raw.period : "last_30",
    one_rep: raw.one_rep === true,
    adherence,
    previous: rate(raw.previous),
    process,
    reps,
    more_reps: typeof raw.more_reps === "number" && raw.more_reps > 0 ? raw.more_reps : 0,
  };
}

export function askCards(turn: { cards?: unknown }): AskCard[] {
  if (!Array.isArray(turn.cards)) return [];
  const out: AskCard[] = [];
  for (const raw of turn.cards) {
    if (!isRecord(raw)) continue;
    const card = raw.kind === "coaching" ? coaching(raw) : raw.kind === "team" ? team(raw) : null;
    if (card) out.push(card);
  }
  return out;
}

/** Change in whole points, or null when either side is unknown. */
export function pointsChange(now: number | null, before: number | null): number | null {
  if (now === null || before === null) return null;
  return Math.round((now - before) * 100);
}

/** The approved answers the reply actually cites, in citation order. */
export function citedPlaybook<T extends { speaker?: string | null }>(evidence: T[]): T[] {
  return evidence.filter((item) => item.speaker === "playbook");
}
