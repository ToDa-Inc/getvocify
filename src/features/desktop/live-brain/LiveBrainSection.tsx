import { LiveTranscript } from "@/features/recording/components";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import type { DesktopMeeting } from "../DesktopMeetingProvider";
import { useLiveBrain } from "../assist/useLiveBrain";
import { LiveBrainPanel } from "./LiveBrainPanel";
import { liveCopy } from "./copy";

/**
 * The dashboard's live view behind the company flag LIVE_BRAIN_ENABLED: the brain's hook and its panel. Mounted only with the
 * flag on, so with it off none of this runs and today's live help (useLiveAssist) is all there is.
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
  const { user } = useAuth();
  // The "Qué decir" view (build contract 2026-10-20): the island draws it and the brain may suggest going deeper.
  const sayView = Boolean(user?.company?.features?.includes("LIVE_SAY_VIEW_ENABLED"));
  const copy = liveCopy(language);
  const types = useTypeOptions();
  const typeKey = meeting.callType.key;
  const typeName = typeKey ? types.options.find((option) => option.key === typeKey)?.label ?? types.labelOf(typeKey) : null;
  const brain = useLiveBrain(
    meeting.turns,
    { flag: true, enabled: helpOn && live && !meeting.paused, helpOn, sayView },
    {
      callId: meeting.callId,
      contactId: meeting.contact?.hubspotId,
      contactName: meeting.contact?.name,
      callMode: meeting.callMode,
      typeKey,
      typeLabel: typeName,
      prospectLevel: meeting.levels.them,
    },
  );
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
