import { AlertTriangle, Check, Mic, Terminal, Volume2 } from "lucide-react";
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
  disabled,
  onAction,
}: {
  type: DesktopPermissionType;
  status: "authorized" | "denied" | "never_requested";
  guideActive: boolean;
  disabled: boolean;
  onAction: () => void;
}) {
  const copy = permissionCopy(type);
  const on = status === "authorized";
  const Icon = type === DESKTOP_PERMISSION.microphone ? Mic : Volume2;
  const isSystem = type === DESKTOP_PERMISSION.systemAudio;

  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 rounded-2xl border px-4 py-3 transition-colors duration-300",
        on ? "border-beige/30 bg-beige/5" : "border-border/70 bg-card/60",
        disabled && !on && "opacity-60",
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
      {!on && !disabled ? (
        <Button
          type="button"
          size="sm"
          variant={isSystem ? "default" : "outline"}
          className="shrink-0 rounded-full"
          disabled={guideActive && isSystem}
          onClick={onAction}
        >
          {guideActive && isSystem ? "Guide open…" : "Allow"}
        </Button>
      ) : null}
    </div>
  );
}

function SigningBlocker() {
  return (
    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 px-4 py-4 text-left">
      <div className="flex gap-3">
        <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-2 text-sm">
          <p className="font-medium text-foreground">This build is unsigned</p>
          <p className="text-muted-foreground leading-relaxed">
            macOS only lists <strong>signed</strong> apps under Screen &amp; System Audio Recording.
            That&apos;s why Settings looks empty — it&apos;s not you, it&apos;s the ad-hoc signature from{" "}
            <code className="text-xs bg-muted px-1 rounded">codesign -s -</code>.
          </p>
          <div className="rounded-xl bg-muted/40 border border-border/60 p-3 font-mono text-xs text-foreground/90 space-y-1">
            <div className="flex items-center gap-2 text-muted-foreground font-sans text-xs mb-1">
              <Terminal className="h-3.5 w-3.5" />
              Terminal (once)
            </div>
            <p>bash ~/getvocify-desktop/scripts/create-dev-signing-cert.sh</p>
            <p>CODESIGN_IDENTITY=&quot;Vocify Dev&quot; ~/getvocify-desktop/scripts/dev-desktop.sh</p>
          </div>
          <p className="text-xs text-muted-foreground">
            The script creates a local <strong>Vocify Dev</strong> cert and trusts it for code signing.
            Then rebuild — Vocify will appear in Settings and drag-to-allow works.
          </p>
        </div>
      </div>
    </div>
  );
}

/** Shown on the Mac app until mic + system audio are ready. */
export function DesktopPermissionsPanel({ className }: { className?: string }) {
  const { available, loading, snapshot, blocker, appName, guideActive, request, guide } =
    useDesktopPermissions();

  if (!available || blocker === "none") return null;

  if (blocker === "signing") {
    return (
      <div
        className={cn(
          `${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-6 md:p-8 mb-6`,
          className,
        )}
      >
        <SigningBlocker />
      </div>
    );
  }

  return (
    <div
      className={cn(
        `${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-6 md:p-8 mb-6 text-left animate-in fade-in duration-300 motion-reduce:animate-none`,
        className,
      )}
    >
      <p className={THEME_TOKENS.typography.capsLabel}>Before your first meeting</p>
      <h2 className="text-xl font-semibold tracking-tight text-foreground mt-1 mb-1">
        Allow mic and meeting audio
      </h2>
      <p className="text-sm text-muted-foreground mb-5 max-w-lg">
        Tap <strong>Allow</strong> on system audio — a panel appears beside Settings so you can drag{" "}
        {appName} into the list (Codex-style).
      </p>

      <div className="space-y-3 max-w-xl">
        <PermissionRow
          type={DESKTOP_PERMISSION.microphone}
          status={snapshot.microphone}
          guideActive={false}
          disabled={false}
          onAction={() => void request(DESKTOP_PERMISSION.microphone)}
        />
        <PermissionRow
          type={DESKTOP_PERMISSION.systemAudio}
          status={snapshot.systemAudio}
          guideActive={guideActive}
          disabled={false}
          onAction={() => void guide(DESKTOP_PERMISSION.systemAudio)}
        />
      </div>

      {snapshot.systemAudio !== "authorized" && snapshot.systemAudioError ? (
        <p className="text-xs text-muted-foreground mt-4 font-mono">{snapshot.systemAudioError}</p>
      ) : null}

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3" aria-live="polite">
          Checking permissions…
        </p>
      ) : null}
    </div>
  );
}
