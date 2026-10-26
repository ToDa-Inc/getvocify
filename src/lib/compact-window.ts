// The dashboard's compact window in the desktop app: during a call the app is a small window at the side of the screen,
// above the call, that shows only the live view (a button opens the whole dashboard). It exists for a call: it comes by
// itself when a recording starts, and once the recording ends the window goes back to its size and the dashboard (the
// call's review) shows as always.
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

/** A recording has just gone live and this call has not had its compact window yet: it comes by itself, once per call
 * (a rep who opened the whole dashboard during the call keeps it). */
export function compactWindowDue(input: { available: boolean; phase: MeetingPhase; callId: string | null; doneFor: string | null }): boolean {
  return input.available && input.phase === "live" && input.callId !== null && input.callId !== input.doneFor;
}
