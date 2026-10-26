import { useEffect, useRef } from "react";
import { compactViewShown, compactWindowDue, compactWindowReleased } from "@/lib/compact-window";
import { getDesktopBridge } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";
import { useDesktopMeeting } from "./DesktopMeetingProvider";
import { useLiveHelp } from "./assist/LiveHelpProvider";
import { CompactLiveView } from "./live-brain/CompactLiveView";
import { liveCopy } from "./live-brain/copy";
import { useCompactWindow } from "./useCompactWindow";

/**
 * The dashboard in the desktop app's compact window. When a recording starts the window turns compact and comes forward
 * by itself, once per call: during a call the app is that small window, and its button opens the whole dashboard (which
 * then stays open for the rest of the call). While it is compact the live view covers the whole page (the dashboard stays
 * mounted underneath, so going back loses nothing). When the call ends the window goes back to its size by itself, and
 * the call's review shows as always.
 */
export function CompactCallWindow() {
  const meeting = useDesktopMeeting();
  const { brain, helpOn, setAssistOn, typeName } = useLiveHelp();
  const { language } = useLanguage();
  const { available, compact, setCompact } = useCompactWindow();

  const doneFor = useRef<string | null>(null);
  const due = compactWindowDue({ available, phase: meeting.phase, callId: meeting.callId, doneFor: doneFor.current });
  useEffect(() => {
    if (!due) return;
    doneFor.current = meeting.callId;
    setCompact(true);
    getDesktopBridge()?.shell.command("show");
  }, [due, meeting.callId, setCompact]);

  const release = compactWindowReleased(compact, meeting.phase);
  useEffect(() => {
    if (release) setCompact(false);
  }, [release, setCompact]);

  if (!compactViewShown(compact, meeting.phase)) return null;
  return (
    // Above the sidebar (z-40) and the dock; under tooltips, menus and dialogs (z-50), which open from inside it.
    <div className="fixed inset-0 z-[45]">
      <CompactLiveView
        meeting={meeting}
        brain={brain}
        copy={liveCopy(language)}
        helpOn={helpOn}
        onHelpChange={setAssistOn}
        typeName={typeName}
        onExpand={() => setCompact(false)}
      />
    </div>
  );
}
