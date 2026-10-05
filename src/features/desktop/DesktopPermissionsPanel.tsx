import { Check, Mic, Volume2 } from "lucide-react";
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

function PermissionRow({
  type,
  status,
  onAction,
}: {
  type: DesktopPermissionType;
  status: "authorized" | "denied" | "never_requested";
  onAction: () => void;
}) {
  const copy = permissionCopy(type);
  const on = status === "authorized";
  const Icon = type === DESKTOP_PERMISSION.microphone ? Mic : Volume2;
  const action = permissionAction(status);
  const label =
    action === "open_settings" ? "Open Settings" : on ? null : "Allow";

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
      {label ? (
        <Button type="button" size="sm" variant="outline" className="shrink-0 rounded-full" onClick={onAction}>
          {label}
        </Button>
      ) : null}
    </div>
  );
}

/** Shown on the desktop app until permissions are ready. */
export function DesktopPermissionsPanel({ className }: { className?: string }) {
  const { available, loading, snapshot, blocker, request } = useDesktopPermissions();
  const platform = desktopPlatform();

  if (!available || blocker === "none") return null;

  const isMac = platform === "darwin";
  const title = isMac ? "Allow mic and meeting audio" : "Allow microphone";
  const description = isMac
    ? "Microphone uses the macOS prompt. For meeting audio, drag Vocify from the card into Screen & System Audio Recording. If it is already listed but off, turn it on, then quit (⌘Q) and reopen."
    : "Vocify needs your microphone to record calls. Go to Settings > Privacy & security > Microphone to allow it.";

  return (
    <div
      className={cn(
        `${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-6 md:p-8 mb-6 text-left animate-in fade-in duration-300 motion-reduce:animate-none`,
        className,
      )}
    >
      <p className={THEME_TOKENS.typography.capsLabel}>Before your first meeting</p>
      <h2 className="text-xl font-semibold tracking-tight text-foreground mt-1 mb-1">{title}</h2>
      <p className="text-sm text-muted-foreground mb-5 max-w-lg">{description}</p>

      <div className="space-y-3 max-w-xl">
        <PermissionRow
          type={DESKTOP_PERMISSION.microphone}
          status={snapshot.microphone}
          onAction={() => void request(DESKTOP_PERMISSION.microphone)}
        />
        {isMac ? (
          <PermissionRow
            type={DESKTOP_PERMISSION.systemAudio}
            status={snapshot.systemAudio}
            onAction={() => void request(DESKTOP_PERMISSION.systemAudio)}
          />
        ) : null}
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3" aria-live="polite">
          Checking permissions…
        </p>
      ) : null}
    </div>
  );
}
