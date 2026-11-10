import { useEffect } from "react";
import { Mic, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DesktopPermissionRows } from "@/features/desktop/DesktopPermissionsPanel";
import { useDesktopMeeting } from "@/features/desktop/DesktopMeetingProvider";
import { useAudioCheck } from "@/features/desktop/useAudioCheck";
import { useDesktopPermissions } from "@/features/desktop/useDesktopPermissions";
import { useDesktopUpdates } from "@/features/desktop/useDesktopUpdates";
import { desktopPlatform, type DesktopUpdateStatus } from "@/lib/desktop-host";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`;

/** One input's live loudness, and whether real sound has come through yet. */
function CheckMeter({ icon: Icon, label, level, heard, running, hint }: {
  icon: typeof Mic;
  label: string;
  level: number;
  heard: boolean;
  running: boolean;
  hint: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm text-foreground">{label}</p>
          <p className={cn("text-xs", heard ? "text-beige" : "text-muted-foreground")} aria-live="polite">
            {heard ? "Coming through" : running ? hint : ""}
          </p>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-beige transition-[width] duration-150 ease-out motion-reduce:transition-none"
            style={{ width: `${Math.round(level * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

/** This computer's own settings: what Vocify may use, a check that audio comes through, the record shortcut. */
const SystemSection = () => {
  const permissions = useDesktopPermissions();
  const meeting = useDesktopMeeting();
  const check = useAudioCheck();
  const updates = useDesktopUpdates();
  const recording = meeting.available && meeting.phase !== "idle";
  const { running, yieldToRecording } = check;

  // A recording started from the island while the check runs takes the one capture over.
  useEffect(() => {
    if (recording && running) yieldToRecording();
  }, [recording, running, yieldToRecording]);
  const isMac = desktopPlatform() === "darwin";

  return (
    <div className="space-y-6">
      <div className={card}>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Permissions</h3>
        <p className="text-xs text-muted-foreground mt-1 mb-5">
          {isMac
            ? "What macOS lets Vocify use on this Mac. Without them, Vocify records silence."
            : "What Windows lets Vocify use on this computer. Without the microphone, Vocify records silence."}
        </p>
        <div className="max-w-xl">
          <DesktopPermissionRows
            permissions={permissions}
            onTestMic={recording ? undefined : () => {
              document.getElementById("audio-check")?.scrollIntoView({ behavior: "smooth", block: "start" });
              if (!check.running) void check.start();
            }}
          />
        </div>
      </div>

      <div id="audio-check" className={`${card} scroll-mt-6`}>
        <div className="flex items-start justify-between gap-6">
          <div>
            <h3 className={THEME_TOKENS.typography.sectionTitle}>Audio check</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Say something, and play a video so Vocify hears the computer's sound. Nothing is recorded.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="rounded-full shrink-0"
            disabled={recording && !check.running}
            onClick={() => (check.running ? check.stop() : void check.start())}
          >
            {check.running ? "Stop" : "Test audio"}
          </Button>
        </div>
        <div className="mt-5 max-w-xl space-y-4">
          <CheckMeter icon={Mic} label="Your mic" level={check.levels.you} heard={check.heard.you} running={check.running} hint="Say something…" />
          <CheckMeter
            icon={Volume2}
            label="Call audio"
            level={check.levels.them}
            heard={check.heard.them}
            running={check.running}
            hint="Play a video…"
          />
        </div>
        {recording ? (
          <p className="text-xs text-muted-foreground mt-4">Available when you're not recording.</p>
        ) : check.problem ? (
          <p className="text-xs text-warning mt-4" role="status">{check.problem.text}</p>
        ) : null}
      </div>

      {updates?.status ? (
        <div className={card}>
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0">
              <h3 className={THEME_TOKENS.typography.sectionTitle}>Updates</h3>
              <p className="text-xs text-muted-foreground mt-1">Vocify {updates.status.version}</p>
              <p
                className={cn("text-sm mt-3", updates.status.state === "failed" ? "text-warning" : "text-foreground")}
                role="status"
                aria-live="polite"
              >
                {updates.mustWait && updates.status.state === "ready"
                  ? `Vocify restarts into ${updates.status.next} when the recording ends.`
                  : updateLine(updates.status)}
              </p>
            </div>
            {updates.status.state === "ready" && updates.install ? (
              <Button type="button" size="sm" className="rounded-full shrink-0" onClick={updates.install}>
                Restart now
              </Button>
            ) : updates.status.state !== "unavailable" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="rounded-full shrink-0"
                disabled={["checking", "downloading", "ready"].includes(updates.status.state)}
                onClick={updates.check}
              >
                Check for updates
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

/** What the Updates card says about where updating stands. */
function updateLine(status: DesktopUpdateStatus): string {
  switch (status.state) {
    case "unavailable":
      return "This copy of Vocify doesn't update itself.";
    case "idle":
    case "checking":
      return "Checking for updates…";
    case "current":
      return `Up to date · checked at ${new Date(status.checkedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    case "downloading":
      return `Downloading ${status.next}…`;
    case "ready":
      return `${status.next} is ready. Vocify restarts into it as soon as nothing is being recorded.`;
    case "failed": {
      const reason = status.reason.split("\n")[0].slice(0, 140);
      return `Couldn't check for updates: ${reason}`;
    }
  }
}

export default SystemSection;
