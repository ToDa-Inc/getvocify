import { LiveTranscript } from "@/features/recording/components";
import { useLanguage } from "@/lib/i18n";
import type { DesktopMeeting } from "../DesktopMeetingProvider";
import { useLiveHelp } from "../assist/LiveHelpProvider";
import { LiveBrainPanel } from "./LiveBrainPanel";
import { liveCopy } from "./copy";

/**
 * The dashboard's live view behind the company flag LIVE_BRAIN_ENABLED: the brain's panel. The brain itself runs for the whole
 * meeting in LiveHelpProvider (the island needs it on every page); this only draws it.
 */
export function LiveBrainSection({
  meeting,
  live,
  helpOn,
  onHelpChange,
}: {
  meeting: DesktopMeeting;
  live: boolean;
  helpOn: boolean;
  onHelpChange: (on: boolean) => void;
}) {
  const { language } = useLanguage();
  const { brain, typeName } = useLiveHelp();
  const copy = liveCopy(language);
  return (
    <LiveBrainPanel
      brain={brain}
      copy={copy}
      helpOn={helpOn}
      onHelpChange={onHelpChange}
      typeName={typeName}
      transcript={
        <LiveTranscript
          finalTranscript=""
          interimTranscript=""
          turns={meeting.turns}
          speaking={meeting.paused ? undefined : { rep: meeting.speaking.you, prospect: meeting.speaking.them }}
          isActive={live}
          listeningHint={copy.transcriptEmpty}
          className="h-full max-h-none rounded-none border-0 bg-transparent px-4 py-3 shadow-none ring-0"
        />
      }
    />
  );
}
