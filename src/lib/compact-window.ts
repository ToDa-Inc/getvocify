// The dashboard's compact window in the desktop app: the whole dashboard shrunk to a small window at the side of the
// screen, above the call, that shows only the live view. It exists for a call: once the recording ends the window goes
// back to its size and the dashboard (the call's review) shows as always.
import type { MeetingPhase } from "@/features/desktop/DesktopMeetingProvider";

/** The phases of a recording the compact window is for. */
const DURING_CALL: readonly MeetingPhase[] = ["starting", "live"];

/** The compact view covers the dashboard: the window is compact and a call is on. */
export function compactViewShown(compact: boolean, phase: MeetingPhase): boolean {
  return compact && DURING_CALL.includes(phase);
}

/** The window is compact but the call is over (or never started): it goes back to its size. */
export function compactWindowReleased(compact: boolean, phase: MeetingPhase): boolean {
  return compact && !DURING_CALL.includes(phase);
}
