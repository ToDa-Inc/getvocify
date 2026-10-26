import { useEffect } from "react";
import { compactViewShown, compactWindowReleased } from "@/lib/compact-window";
import { useLanguage } from "@/lib/i18n";
import { useDesktopMeeting } from "./DesktopMeetingProvider";
import { useLiveHelp } from "./assist/LiveHelpProvider";
import { CompactLiveView } from "./live-brain/CompactLiveView";
import { liveCopy } from "./live-brain/copy";
import { useCompactWindow } from "./useCompactWindow";

/**
 * The dashboard in the desktop app's compact window: while it is compact and a call is on, the live view covers the
 * whole page (the dashboard stays mounted underneath, so going back loses nothing). When the call ends the window goes
 * back to its size by itself, and the call's review shows as always.
 */
export function CompactCallWindow() {
  const meeting = useDesktopMeeting();
  const { brain, helpOn, typeName } = useLiveHelp();
  const { language } = useLanguage();
  const { compact, setCompact } = useCompactWindow();

  const release = compactWindowReleased(compact, meeting.phase);
  useEffect(() => {
    if (release) setCompact(false);
  }, [release, setCompact]);

  if (!compactViewShown(compact, meeting.phase)) return null;
  return (
    <div className="fixed inset-0 z-[60]">
      <CompactLiveView
        meeting={meeting}
        brain={brain}
        copy={liveCopy(language)}
        helpOn={helpOn}
        typeName={typeName}
        onExpand={() => setCompact(false)}
      />
    </div>
  );
}
