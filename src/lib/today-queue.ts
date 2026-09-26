import {
  homeSelection,
  homeSelectionInReview,
  homeSelectionLocked,
  selectedRow,
  type HomeRow,
} from "../../shared/ui/home.js";
import { initialQueue, prefetchTarget, queueReducer, currentItem } from "../../shared/ui/queue.js";
import type { TodayItem } from "./today";

export type TodayQueueState = ReturnType<typeof queueReducer>;

export { initialQueue, queueReducer, currentItem };

export type HomeSelectionState = ReturnType<typeof homeSelection>;

export type CallEndedEvent = {
  answered?: boolean;
  memoId?: string | null;
  screeningOutcome?: string | null;
  callStatus?: "failed";
  callSid?: string | null;
};

export type CallResolvedEvent = { outcome: "no_answer" | "failed"; callSid?: string | null };

export function todayQueueStart(items: TodayItem[]): TodayQueueState {
  return queueReducer(initialQueue, { type: "start", items });
}

export type TodayQueueStepEvent = { type: "skip" } | { type: "exit" };

export function todayQueueStep(state: TodayQueueState, event: TodayQueueStepEvent): TodayQueueState {
  return queueReducer(state, event);
}

export function homeQueueStartCall(state: HomeSelectionState): HomeSelectionState {
  return homeSelection(state, { type: "call" });
}

export function homeQueueCallEnded(state: HomeSelectionState, event: CallEndedEvent): HomeSelectionState {
  return homeSelection(state, { type: "call_ended", ...event });
}

export function homeQueueCallResolved(state: HomeSelectionState, event: CallResolvedEvent): HomeSelectionState {
  return homeSelection(state, { type: "call_resolved", ...event });
}

export function homeQueueReviewed(state: HomeSelectionState): HomeSelectionState {
  return homeSelection(state, { type: "reviewed" });
}

export function homeQueueLocked(state: HomeSelectionState): boolean {
  return homeSelectionLocked(state);
}

export function homeQueueInReview(state: HomeSelectionState): boolean {
  return homeSelectionInReview(state);
}

export function homeQueueNextRow(state: HomeSelectionState, rows: HomeRow[]): HomeRow | null {
  if (!homeSelectionInReview(state)) return null;
  const keys = rows.map((row) => row.key);
  const targetKey = prefetchTarget({ mode: "review", items: keys, index: state.index });
  if (!targetKey || typeof targetKey !== "string") return null;
  return rows.find((row) => row.key === targetKey) ?? null;
}

export function homeQueueSelectedRow(state: HomeSelectionState, rows: HomeRow[]): HomeRow | null {
  return selectedRow(state, rows);
}
