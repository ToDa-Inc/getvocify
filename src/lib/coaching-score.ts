/** The memo shows the stored score. The browser does not recompute it. */

import type { ProductTranslations } from "./product-catalog";

export type ScoreView = {
  status: string;
  value: number | null;
  reason: string | null;
  adherence: number | null;
  coverage: number | null;
  strengths?: string[];
  improvements?: string[];
  crm_outcome?: string | null;
  met_steps?: number;
  /** PLAYBOOK_QUALIFICATION_ENABLED: the mark split by block (plan §15). */
  blocks?: Partial<Record<ScoreBlock, { met: number; applicable: number }>> | null;
};

export type ScoreBlock = "steps" | "qualification" | "objections";
const BLOCK_ORDER: ScoreBlock[] = ["steps", "qualification", "objections"];

/** "7/10 · Pasos 4/5 · Cualificación 2/4 · Objeciones 1/1": blocks that applied to this call
 * only. Without blocks, just the mark; null when there is no mark. */
export function scoreBlocksLine(
  score: Pick<ScoreView, "value" | "blocks">,
  copy: { scoreOf: string; blocks: Record<ScoreBlock, string> },
): string | null {
  if (score.value === null || score.value === undefined) return null;
  const parts = [copy.scoreOf.replace("{value}", String(score.value))];
  for (const block of BLOCK_ORDER) {
    const part = score.blocks?.[block];
    if (part && part.applicable > 0) parts.push(`${copy.blocks[block]} ${part.met}/${part.applicable}`);
  }
  return parts.join(" · ");
}

export type CoachingSurface =
  | { kind: "setup"; title: string; action: string | null }
  | { kind: "waiting"; title: string }
  | { kind: "internal"; title: string }
  | { kind: "unscored"; title: string; strengths: string[]; improvements: string[]; coverage: number | null }
  | { kind: "scored"; strengths: string[]; improvements: string[]; value: number; adherence: number | null; crmOutcome: string | null };

export type CoachingProductCopy = Pick<
  ProductTranslations,
  | "coachingSetupTitle"
  | "coachingSetupAction"
  | "coachingWaitingTitle"
  | "coachingInternalTitle"
  | "coachingUnscoredTitle"
>;

export function coachingSurface(score: ScoreView, copy: CoachingProductCopy, role: string): CoachingSurface {
  if (score.reason === "missing_playbook") {
    const canEdit = role === "owner" || role === "admin";
    return {
      kind: "setup",
      title: copy.coachingSetupTitle,
      action: canEdit ? copy.coachingSetupAction : null,
    };
  }
  // An internal memo (no customer in it) is never scored: say so rather than wait for a score.
  if (score.reason === "internal") {
    return { kind: "internal", title: copy.coachingInternalTitle };
  }
  if (score.reason === "not_scored") {
    return { kind: "waiting", title: copy.coachingWaitingTitle };
  }
  if (score.value === null) {
    return {
      kind: "unscored",
      title: copy.coachingUnscoredTitle,
      strengths: score.strengths ?? [],
      improvements: score.improvements ?? [],
      coverage: score.coverage,
    };
  }
  return {
    kind: "scored",
    strengths: score.strengths ?? [],
    improvements: score.improvements ?? [],
    value: score.value,
    adherence: score.adherence,
    crmOutcome: score.crm_outcome ?? null,
  };
}
