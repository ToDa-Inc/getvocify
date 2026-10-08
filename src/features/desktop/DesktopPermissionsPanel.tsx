import { AppWindow, Check, Mic, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DESKTOP_PERMISSION,
  permissionAction,
  permissionCopy,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { desktopPlatform } from "@/lib/desktop-host";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { useDesktopPermissions } from "./useDesktopPermissions";

type Permissions = ReturnType<typeof useDesktopPermissions>;

function PermissionRow({
  type,
  status,
  onAction,
  note,
  onRelaunch,
}: {
  type: DesktopPermissionType;
  status: "authorized" | "denied" | "never_requested";
  onAction: () => void;
  /** Replaces the body while the permission is off (the next step after Settings). */
  note?: string;
  /** Shown beside the action once a restart is what's left. */
  onRelaunch?: () => void;
}) {
  const copy = permissionCopy(type);
  const on = status === "authorized";
  const Icon =
    type === DESKTOP_PERMISSION.microphone ? Mic : type === DESKTOP_PERMISSION.crmTabs ? AppWindow : Volume2;
  const action = permissionAction(status);
  const label =
    action === "open_settings" || onRelaunch ? "Open Settings" : on ? null : "Allow";

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
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed" aria-live="polite">
            {on ? copy.enabledBody : note ?? copy.enableBody}
          </p>
        </div>
      </div>
      {label ? (
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            type="button"
            size="sm"
            variant={onRelaunch ? "ghost" : "outline"}
            className="rounded-full"
            onClick={onAction}
          >
            {label}
          </Button>
          {onRelaunch ? (
            <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={onRelaunch}>
              Relaunch
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const SYSTEM_AUDIO_NOTE = {
  relaunch: "Switched it on? Relaunch Vocify to apply it.",
  stuck: "Still off. In Settings, remove Vocify with −, add it again with +, then relaunch.",
  reopen: "Switched it on? Quit Vocify and open it again.",
} as const;

const CRM_TABS_NOTE = "Open Chrome, Safari, Arc, Edge or Brave, then Allow.";

const WINDOWS_MIC_NOTE =
  'Vocify needs your microphone to record calls. In Windows Settings, open Privacy & security > Microphone and turn on "Let desktop apps access your microphone".';

/** Microphone + system audio rows, with the relaunch step macOS needs for system audio. */
export function DesktopPermissionRows({ permissions }: { permissions: Permissions }) {
  const { snapshot, request, systemAudioHint, canRelaunch, relaunch } = permissions;
  const hint = systemAudioHint === "none" ? null : canRelaunch ? systemAudioHint : "reopen";

  return (
    <div className="space-y-3">
      <PermissionRow
        type={DESKTOP_PERMISSION.microphone}
        status={snapshot.microphone}
        onAction={() => void request(DESKTOP_PERMISSION.microphone)}
      />
      {/* Windows captures the call's audio without a permission: only the Mac asks for it. */}
      {desktopPlatform() !== "win32" ? (
        <PermissionRow
          type={DESKTOP_PERMISSION.systemAudio}
          status={snapshot.systemAudio}
          onAction={() => void request(DESKTOP_PERMISSION.systemAudio)}
          note={hint ? SYSTEM_AUDIO_NOTE[hint] : undefined}
          onRelaunch={hint && hint !== "reopen" ? () => void relaunch() : undefined}
        />
      ) : null}
      {snapshot.crmTabs ? (
        <PermissionRow
          type={DESKTOP_PERMISSION.crmTabs}
          status={snapshot.crmTabs === "unavailable" ? "never_requested" : snapshot.crmTabs}
          onAction={() => void request(DESKTOP_PERMISSION.crmTabs)}
          note={snapshot.crmTabs === "unavailable" ? CRM_TABS_NOTE : undefined}
        />
      ) : null}
    </div>
  );
}

/** Shown on the desktop app until permissions are ready. */
export function DesktopPermissionsPanel({ className }: { className?: string }) {
  const permissions = useDesktopPermissions();
  const { available, loading, blocker } = permissions;
  const platform = desktopPlatform();

  if (!available || blocker === "none") return null;

  const isMac = platform === "darwin";
  const title = isMac ? "Allow mic and meeting audio" : "Allow microphone";

  return (
    <div
      className={cn(
        `${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-6 md:p-8 mb-6 text-left animate-in fade-in duration-300 motion-reduce:animate-none`,
        className,
      )}
    >
      <p className={THEME_TOKENS.typography.capsLabel}>Before your first meeting</p>
      <h2 className="text-xl font-semibold tracking-tight text-foreground mt-1 mb-1">{title}</h2>
      <p className="text-sm text-muted-foreground mb-5 max-w-lg">
        {isMac ? (
          <>
            Microphone uses the macOS prompt. For meeting audio, drag <strong>Vocify</strong> from the card
            into Screen &amp; System Audio Recording, or turn it on if it is already listed.
          </>
        ) : (
          WINDOWS_MIC_NOTE
        )}
      </p>

      <div className="max-w-xl">
        <DesktopPermissionRows permissions={permissions} />
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3" aria-live="polite">
          Checking permissions…
        </p>
      ) : null}
    </div>
  );
}
