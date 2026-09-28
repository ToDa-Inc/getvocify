import { Link, useLocation } from "react-router-dom";
import { ROUTES } from "@/shared/lib/constants";
import { useDesktopMeeting } from "./DesktopMeetingProvider";

/** Keeps a live or unsent meeting reachable from any dashboard page. */
export function DesktopRecordingChip() {
  const meeting = useDesktopMeeting();
  const { pathname } = useLocation();
  if (pathname === ROUTES.RECORD || pathname === ROUTES.DASHBOARD) return null;

  if (meeting.phase === "live") {
    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-destructive/20 bg-destructive/10 py-1 pl-3 pr-1 text-xs font-medium text-destructive animate-in fade-in duration-200 motion-reduce:animate-none">
        <span className="h-1.5 w-1.5 rounded-full bg-destructive animate-pulse" />
        <Link to={ROUTES.RECORD} className="tabular-nums hover:underline">
          {meeting.elapsed}
        </Link>
        <button
          type="button"
          onClick={() => void meeting.stop()}
          className="rounded-full bg-destructive px-2.5 py-0.5 text-destructive-foreground transition-colors hover:bg-destructive/90"
        >
          Stop
        </button>
      </div>
    );
  }

  if (meeting.phase === "idle" && meeting.pending.length) {
    return (
      <Link
        to={ROUTES.RECORD}
        className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-card py-1 px-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground animate-in fade-in duration-200 motion-reduce:animate-none"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-beige" />
        {meeting.pending.length === 1 ? "Meeting not sent" : `${meeting.pending.length} meetings not sent`}
      </Link>
    );
  }

  return null;
}
