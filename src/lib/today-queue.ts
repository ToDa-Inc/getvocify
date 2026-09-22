import { initialQueue, queueReducer, currentItem } from "../../shared/ui/queue.js";
import type { TodayItem } from "./today";

export type TodayQueueState = ReturnType<typeof queueReducer>;

export { initialQueue, queueReducer, currentItem };

export function todayQueueStart(items: TodayItem[]): TodayQueueState {
  return queueReducer(initialQueue, { type: "start", items });
}

export type TodayQueueStepEvent = { type: "skip" } | { type: "exit" };

export function todayQueueStep(state: TodayQueueState, event: TodayQueueStepEvent): TodayQueueState {
  return queueReducer(state, event);
}
