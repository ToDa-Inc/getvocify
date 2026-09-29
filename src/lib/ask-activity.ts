import type { AskStep } from "./ask-thread.ts";

/**
 * A step that failed and was followed by another step was retried: the reader needs the outcome, not the
 * stumble. Only a failure that nothing followed stays visible.
 */
export function visibleSteps(steps: AskStep[]): AskStep[] {
  return steps.filter((step, index) => step.status !== "failed" || index === steps.length - 1);
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
