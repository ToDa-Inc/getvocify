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
};

export type CoachingSurface =
  | { kind: "setup"; title: string; action: string | null }
  | { kind: "waiting"; title: string }
  | { kind: "unscored"; title: string; strengths: string[]; improvements: string[]; coverage: number | null }
  | { kind: "scored"; strengths: string[]; improvements: string[]; value: number; adherence: number | null; crmOutcome: string | null };

export type CoachingProductCopy = Pick<
  ProductTranslations,
  "coachingSetupTitle" | "coachingSetupAction" | "coachingWaitingTitle" | "coachingUnscoredTitle"
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
