import { useSyncExternalStore } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { callEngine } from "@/features/calling/callEngine";
import { useDesktopMeeting } from "@/features/desktop/DesktopMeetingProvider";
import { isCallUp } from "@/lib/call-engine-state";
import { useLanguage } from "@/lib/i18n";
import { ROUTES } from "@/shared/lib/constants";

/**
 * Starts a recording from Inicio without leaving it: the island opens and the page (the chat included)
 * stays where it is. While it records, this becomes the live clock and Stop, since the dashboard chip
 * is hidden on Inicio. Only in the desktop app: a browser has no island. A start that fails (usually a
 * missing permission) hands over to the record page, which carries the permissions panel.
 */
export function HomeRecordButton() {
  const { t } = useLanguage();
  const home = t.product.home;
  const navigate = useNavigate();
  const meeting = useDesktopMeeting();
  const onCall = isCallUp(useSyncExternalStore(callEngine.subscribe, callEngine.getState));
  if (!meeting.available) return null;

  if (meeting.phase === "live") {
    return (
      <div
        role="group"
        aria-label={home.recording}
        className="mr-1.5 inline-flex h-8 items-center gap-2 rounded-full border border-destructive/20 bg-destructive/10 pl-3 pr-1 text-[13px] font-medium text-destructive animate-in fade-in duration-200 motion-reduce:animate-none"
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-destructive animate-pulse motion-reduce:animate-none" />
        <Link to={ROUTES.RECORD} className="tabular-nums hover:underline">
          {meeting.elapsed}
        </Link>
        <Button variant="recording" size="text" className="h-6 rounded-full px-2.5 text-xs" onClick={() => void meeting.stop()}>
          {home.stopRecording}
        </Button>
      </div>
    );
  }

  if (meeting.phase !== "idle") {
    return (
      <span role="status" aria-label={home.recording} className="mr-1.5 inline-flex h-8 items-center px-2.5">
        <VocifySpinner size={14} />
      </span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="outline"
          size="text"
          className="mr-1.5 h-8 px-3"
          disabled={onCall}
          onClick={() => void meeting.startHere().then((live) => (live ? undefined : navigate(ROUTES.RECORD)))}
        >
          <Mic aria-hidden strokeWidth={1.5} />
          {home.record}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{home.recordTip}</TooltipContent>
    </Tooltip>
  );
}
