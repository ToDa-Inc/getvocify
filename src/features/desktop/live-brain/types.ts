import type { emptyLiveState } from "../../../../shared/live-call/state.js";

export type LiveState = ReturnType<typeof emptyLiveState>;

export type LivePoint = LiveState["points"][number];
