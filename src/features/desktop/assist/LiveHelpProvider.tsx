import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useAuth } from "@/features/auth";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import { getDesktopBridge } from "@/lib/desktop-host";
import { clockSeconds } from "@/lib/live-brain";
import { liveHelpActive } from "@/lib/live-call-type";
import { useDesktopMeeting } from "../DesktopMeetingProvider";
import { useLiveAssist, useLiveAssistEnabled } from "./useLiveAssist";
import { useLiveBrain } from "./useLiveBrain";

/** The company flag of the live call assistant (one brain: points, progress, recap). Off: today's live help. */
const LIVE_BRAIN_FLAG = "LIVE_BRAIN_ENABLED";
/** The "Qué decir" view (build contract 2026-10-20): the island draws it and the brain may suggest going deeper. */
const LIVE_SAY_VIEW_FLAG = "LIVE_SAY_VIEW_ENABLED";
/** The strategic card (pilot, with "Qué decir"): the automatic readings write ONE card or nothing. */
const LIVE_CARD_FLAG = "LIVE_CARD_ENABLED";

export type LiveHelp = {
  /** The company has the live call assistant (else today's live help, `assist`). */
  brainOn: boolean;
  /** The remembered switch, and the rep's way to change it. */
  assistOn: boolean;
  setAssistOn: (on: boolean) => void;
  /** Help is on for this call: the switch, unless the rep flipped it in the island; never on an internal call. */
  helpOn: boolean;
  /** Today's live help (the brain off). */
  assist: ReturnType<typeof useLiveAssist>;
  /** The live call assistant (the brain on). */
  brain: ReturnType<typeof useLiveBrain>;
  /** The call type's name as the rep sees it. */
  typeName: string | null;
};

const LiveHelpContext = createContext<LiveHelp | null>(null);

/**
 * Live help for the meeting being recorded, for as long as it lasts: it reads the call, holds what it found and keeps the
 * island told, whatever page the dashboard shows (or with its window closed). The live view only draws what is here. It used
 * to run inside that view, so leaving the Record page stopped it and the island fell back to its plain recording.
 */
export function LiveHelpProvider({ children }: { children: ReactNode }) {
  const meeting = useDesktopMeeting();
  const live = meeting.phase === "live";
  const { user } = useAuth();
  const features = user?.company?.features;
  const brainOn = Boolean(features?.includes(LIVE_BRAIN_FLAG));
  const sayView = Boolean(features?.includes(LIVE_SAY_VIEW_FLAG));
  const card = Boolean(features?.includes(LIVE_CARD_FLAG));
  const [assistOn, setAssistOn] = useLiveAssistEnabled();
  const helpOn = liveHelpActive({ remembered: assistOn, override: meeting.liveHelpOverride, typeKey: meeting.callType.key });
  const typeKey = meeting.callType.key;
  const types = useTypeOptions();
  const typeName = typeKey ? types.options.find((option) => option.key === typeKey)?.label ?? types.labelOf(typeKey) : null;
  const running = helpOn && live && !meeting.paused;

  const assist = useLiveAssist(meeting.turns, running && !brainOn, {
    contactId: meeting.contact?.hubspotId,
    callMode: meeting.callMode,
    callId: meeting.callId,
    typeKey,
    prospectLevel: meeting.levels.them,
  });
  const brain = useLiveBrain(
    meeting.turns,
    { flag: brainOn, enabled: running, helpOn, sayView, card },
    {
      callId: meeting.callId,
      contactId: meeting.contact?.hubspotId,
      contactName: meeting.contact?.name,
      callMode: meeting.callMode,
      typeKey,
      typeLabel: typeName,
      prospectLevel: meeting.levels.them,
      clockSeconds: clockSeconds(meeting.elapsed),
    },
  );

  useEffect(() => {
    getDesktopBridge()?.shell.setState({ liveHelp: helpOn });
  }, [helpOn]);

  // The island shows today's live card while it is open.
  useEffect(() => {
    const card = assist.active;
    getDesktopBridge()?.shell.setState({
      assist: card ? { label: card.label, kind: card.kind, stage: card.stage, bridge: card.bridge, sayThis: card.sayThis } : null,
    });
  }, [assist.active]);

  return (
    <LiveHelpContext.Provider value={{ brainOn, assistOn, setAssistOn, helpOn, assist, brain, typeName }}>
      {children}
    </LiveHelpContext.Provider>
  );
}

export function useLiveHelp(): LiveHelp {
  const help = useContext(LiveHelpContext);
  if (!help) throw new Error("useLiveHelp outside LiveHelpProvider");
  return help;
}
