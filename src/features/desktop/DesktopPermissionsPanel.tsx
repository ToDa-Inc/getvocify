import { Check, Mic, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DESKTOP_PERMISSION,
  permissionAction,
  permissionCopy,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { useDesktopPermissions } from "./useDesktopPermissions";

function PermissionRow({
  type,
  status,
  onEnable,
  onOpenSettings,
}: {
  type: DesktopPermissionType;
  status: "authorized" | "denied" | "never_requested";
  onEnable: () => void;
  onOpenSettings: () => void;
}) {
  const copy = permissionCopy(type);
  const on = status === "authorized";
  const action = permissionAction(status);
  const Icon = type === DESKTOP_PERMISSION.microphone ? Mic : Volume2;

  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 rounded-2xl border px-4 py-3 transition-colors duration-300",
        on ? "border-beige/30 bg-beige/5" : "border-border/70 bg-card/60",
      )}
    >
      <div className="flex gap-3 min-w-0">
        <div
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
            on ? "bg-beige/15 text-beige" : "bg-muted text-muted-foreground",
          )}
        >
          {on ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
        </div>
        <div className="min-w-0 text-left">
          <p className="text-sm font-medium text-foreground">{on ? copy.enabledLabel : copy.enableLabel}</p>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{on ? copy.enabledBody : copy.enableBody}</p>
        </div>
      </div>
      {!on ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="shrink-0 rounded-full"
          onClick={() => (action === "open_settings" ? onOpenSettings() : onEnable())}
        >
          {action === "open_settings" ? "Open Settings" : "Enable"}
        </Button>
      ) : null}
    </div>
  );
}

/** Visual guide: drag Vocify into Screen & System Audio Recording. */
function SystemAudioDropGuide({ appName, onOpenSettings }: { appName: string; onOpenSettings: () => void }) {
  return (
    <div className="mt-3 rounded-2xl border border-dashed border-border/80 bg-muted/15 p-4 text-left">
      <p className="text-xs font-medium text-foreground mb-3">
        In System Settings → Privacy &amp; Security → Screen &amp; System Audio Recording
      </p>
      <div className="flex items-stretch gap-3">
        <button
          type="button"
          onClick={onOpenSettings}
          className="group flex flex-col items-center gap-2 rounded-xl border border-border/70 bg-card px-3 py-3 shadow-sm transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98] cursor-grab active:cursor-grabbing"
          title="Opens System Settings"
        >
          <div className="h-10 w-10 rounded-xl bg-beige/15 flex items-center justify-center text-xs font-semibold text-beige">
            V
          </div>
          <span className="text-[10px] font-medium text-muted-foreground max-w-[72px] text-center leading-tight">
            {appName}
          </span>
        </button>

        <div className="flex items-center text-muted-foreground/50" aria-hidden>
          <svg width="28" height="16" viewBox="0 0 28 16" fill="none" className="opacity-70">
            <path d="M0 8h20M16 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <div
          className="flex-1 min-w-0 rounded-xl border-2 border-dashed border-beige/35 bg-beige/5 px-3 py-4 flex flex-col items-center justify-center gap-1.5"
          onClick={onOpenSettings}
          onKeyDown={(e) => e.key === "Enter" && onOpenSettings()}
          role="button"
          tabIndex={0}
        >
          <p className="text-xs font-medium text-beige">Drop here</p>
          <p className="text-[10px] text-muted-foreground text-center leading-snug">
            or toggle {appName} on
          </p>
        </div>
      </div>
      <Button type="button" variant="link" size="sm" className="mt-3 h-auto p-0 text-xs text-beige" onClick={onOpenSettings}>
        Open System Settings
      </Button>
    </div>
  );
}

/** Shown on the Mac app until mic + system audio are ready. Polls until both pass. */
export function DesktopPermissionsPanel({ className }: { className?: string }) {
  const { available, loading, snapshot, ready, appName, request, openSettings } = useDesktopPermissions();

  if (!available || ready) return null;

  const showDropGuide = snapshot.systemAudio !== "authorized";

  return (
    <div
      className={cn(
        `${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-6 md:p-8 mb-6 text-left animate-in fade-in duration-300 motion-reduce:animate-none`,
        className,
      )}
    >
      <p className={THEME_TOKENS.typography.capsLabel}>Before your first meeting</p>
      <h2 className="text-xl font-semibold tracking-tight text-foreground mt-1 mb-1">
        Hear the call, not the <span className={THEME_TOKENS.typography.accentTitle}>screen</span>
      </h2>
      <p className="text-sm text-muted-foreground mb-5 max-w-lg">
        Two permissions, then you&apos;re set. Vocify never records your screen — only meeting audio.
      </p>

      <div className="space-y-3 max-w-xl">
        <PermissionRow
          type={DESKTOP_PERMISSION.microphone}
          status={snapshot.microphone}
          onEnable={() => void request(DESKTOP_PERMISSION.microphone)}
          onOpenSettings={() => void openSettings(DESKTOP_PERMISSION.microphone)}
        />
        <PermissionRow
          type={DESKTOP_PERMISSION.systemAudio}
          status={snapshot.systemAudio}
          onEnable={() => void request(DESKTOP_PERMISSION.systemAudio)}
          onOpenSettings={() => void openSettings(DESKTOP_PERMISSION.systemAudio)}
        />
      </div>

      {showDropGuide ? (
        <SystemAudioDropGuide
          appName={appName}
          onOpenSettings={() => void openSettings(DESKTOP_PERMISSION.systemAudio)}
        />
      ) : null}

      {snapshot.systemAudio !== "authorized" ? (
        <p className="text-xs text-muted-foreground mt-4 max-w-lg">
          Already enabled {appName}? Quit Vocify (<kbd className="px-1 py-0.5 rounded bg-muted text-[10px]">⌘Q</kbd>
          ) and open it again — macOS only applies this permission after a restart.
        </p>
      ) : null}

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3" aria-live="polite">
          Checking permissions…
        </p>
      ) : null}
    </div>
  );
}
