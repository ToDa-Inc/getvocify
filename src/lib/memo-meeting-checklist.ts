export type MeetingChecklistPayload = {
  observed?: number;
  applicable?: number;
  steps?: Array<{
    step_id?: string;
    label?: string;
    status?: string;
    evidence_refs?: string[];
  }>;
};

export type MeetingChecklistCopy = {
  progressTemplate: string;
  doneLabel: string;
};

export type MeetingChecklistStepView =
  | { kind: "met"; label: string; doneLabel: string }
  | { kind: "pending"; label: string };

export type MeetingChecklistView = {
  progress: string;
  steps: MeetingChecklistStepView[];
};

/** Pure show/hide and row model for memo review checklist (no invented steps). */
export function memoMeetingChecklistView(
  checklist: MeetingChecklistPayload | null | undefined,
  copy: MeetingChecklistCopy,
): MeetingChecklistView | null {
  if (!checklist || typeof checklist !== "object") return null;
  const applicable = Number(checklist.applicable);
  if (!Number.isFinite(applicable) || applicable <= 0) return null;

  const observedRaw = Number(checklist.observed);
  const observed = Number.isFinite(observedRaw) ? observedRaw : 0;
  const progress = copy.progressTemplate
    .replace("{met}", String(observed))
    .replace("{applicable}", String(applicable));

  const doneLabel = String(copy.doneLabel ?? "");
  const steps: MeetingChecklistStepView[] = [];
  for (const step of Array.isArray(checklist.steps) ? checklist.steps : []) {
    const label = String(step?.label ?? "").trim();
    if (!label) continue;
    if (step?.status === "met") {
      steps.push({ kind: "met", label, doneLabel });
    } else {
      steps.push({ kind: "pending", label });
    }
  }

  return { progress, steps };
}
