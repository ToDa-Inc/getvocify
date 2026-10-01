import type { AskStep } from "./ask-thread.ts";

/**
 * A step that failed and was followed by another step was retried: the reader needs the outcome, not the
 * stumble. Only a failure that nothing followed stays visible.
 */
export function visibleSteps(steps: AskStep[]): AskStep[] {
  return steps.filter((step, index) => step.status !== "failed" || index === steps.length - 1);
}

/**
 * The one step to show while the assistant works: the one running now (the latest, if several), else the
 * last one. The line is overwritten as the work moves on instead of growing into a list.
 */
export function currentStep(steps: AskStep[]): AskStep | null {
  for (let index = steps.length - 1; index >= 0; index--) {
    if (steps[index].status === "running") return steps[index];
  }
  return steps.at(-1) ?? null;
}

/**
 * The steps once the answer is in, each kind of work once (by what the reader sees, `labelOf`): repeated
 * lookups of the same thing read as one. First-seen order; each keeps the status of its latest run.
 */
export function distinctSteps(steps: AskStep[], labelOf: (step: AskStep) => string): AskStep[] {
  const byLabel = new Map<string, AskStep>();
  for (const step of steps) {
    const label = labelOf(step);
    const first = byLabel.get(label);
    byLabel.set(label, first ? { ...step, id: first.id } : step);
  }
  return [...byLabel.values()];
}

/**
 * How much of the answer to show after `elapsedMs`, so text glides instead of arriving in bursts.
 * A steady trickle types at a readable pace; a backlog is caught up in about a fifth of a second.
 */
export function nextShown(shown: number, target: number, elapsedMs: number): number {
  if (shown >= target) return target;
  const backlog = target - shown;
  const perSecond = Math.max(90, backlog * 5);
  return Math.min(target, shown + Math.max(1, Math.round((perSecond * Math.max(elapsedMs, 0)) / 1000)));
}
