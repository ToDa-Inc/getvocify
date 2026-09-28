import { Check, GripVertical, Mic, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DESKTOP_PERMISSION,
  permissionCopy,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { useDesktopPermissions } from "./useDesktopPermissions";

function PermissionRow({
  type,
  status,
  guideActive,
  onAction,
}: {
  type: DesktopPermissionType;
  status: "authorized" | "denied" | "never_requested";
  guideActive: boolean;
  onAction: () => void;
}) {
  const copy = permissionCopy(type);
  const on = status === "authorized";
  const Icon = type === DESKTOP_PERMISSION.microphone ? Mic : Volume2;
  const usesDragGuide = type === DESKTOP_PERMISSION.systemAudio;

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
          variant={usesDragGuide ? "default" : "outline"}
          className="shrink-0 rounded-full gap-1.5"
          disabled={guideActive && usesDragGuide}
          onClick={onAction}
        >
          {usesDragGuide ? (
            <>
              <GripVertical className="h-3.5 w-3.5 opacity-70" />
              {guideActive ? "Guide open…" : "Allow"}
            </>
          ) : (
            "Allow"
          )}
        </Button>
      ) : null}
    </div>
  );
}

/** Shown on the Mac app until mic + system audio are ready. */
export function DesktopPermissionsPanel({ className }: { className?: string }) {
  const { available, loading, snapshot, ready, appName, guideActive, request, guide } =
    useDesktopPermissions();

  if (!available || ready) return null;

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
        Allow opens a floating card next to System Settings — drag {appName} into the list, like Codex.
      </p>

      <div className="space-y-3 max-w-xl">
        <PermissionRow
          type={DESKTOP_PERMISSION.microphone}
          status={snapshot.microphone}
          guideActive={false}
          onAction={() => void request(DESKTOP_PERMISSION.microphone)}
        />
        <PermissionRow
          type={DESKTOP_PERMISSION.systemAudio}
          status={snapshot.systemAudio}
          guideActive={guideActive}
          onAction={() => void guide(DESKTOP_PERMISSION.systemAudio)}
        />
      </div>

      {snapshot.systemAudio !== "authorized" ? (
        <div className="mt-4 rounded-xl border border-dashed border-border/70 bg-muted/10 px-4 py-3 text-xs text-muted-foreground leading-relaxed max-w-lg">
          <p className="font-medium text-foreground mb-1">System audio uses drag &amp; drop</p>
          <p>
            Tap <strong>Allow</strong> on system audio. A panel appears beside Settings — drag the{" "}
            {appName} icon into <strong>Screen &amp; System Audio Recording</strong>.
          </p>
          <p className="mt-2">
            Already toggled it on? Quit Vocify (<kbd className="px-1 py-0.5 rounded bg-muted text-[10px]">⌘Q</kbd>
            ) and reopen once.
          </p>
        </div>
      ) : null}

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3" aria-live="polite">
          Checking permissions…
        </p>
      ) : null}
    </div>
  );
}
