// Runs one of state.js's merges from outside JavaScript (the backend's evals carry the state through a call with the same
// code the dashboard uses, not a copy): reads {"op", "state", "result"?, "args"?} on stdin, writes the new state.
import { applyPoints, applyProgress, applyRewrite, dismissPoint, emptyLiveState, pointsIn, progressIn, tick, untick } from "./state.js";

const input = JSON.parse(await new Promise((resolve) => {
  let text = "";
  process.stdin.on("data", (chunk) => (text += chunk));
  process.stdin.on("end", () => resolve(text));
}));
const { op, state, result, args = {} } = input;
const ops = {
  empty: () => emptyLiveState(args.call_id ?? ""),
  applyPoints: () => applyPoints(state, result, args),
  applyProgress: () => applyProgress(state, result),
  applyRewrite: () => applyRewrite(state, result),
  dismissPoint: () => dismissPoint(state, args.id),
  tick: () => tick(state, args.id, args.kind),
  untick: () => untick(state, args.id, args.kind),
  pointsIn: () => pointsIn(state),
  progressIn: () => progressIn(state),
};
if (!ops[op]) throw new Error(`unknown op ${op}`);
process.stdout.write(JSON.stringify(ops[op]()));
