import { AlertCircle, ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CallAudioFix } from "@/lib/audio-fix";
import { cn } from "@/lib/utils";

/** A small macOS switch, as it looks in System Settings. */
function MiniSwitch({ on }: { on: boolean }) {
  return (
    <span
      className={cn(
        "relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors",
        on ? "bg-beige" : "bg-muted-foreground/30",
      )}
      aria-hidden
    >
      <span className={cn("absolute h-3 w-3 rounded-full bg-white shadow-xs", on ? "left-[13px]" : "left-0.5")} />
    </span>
  );
}

/** The − and + under the app list in System Settings. */
function MiniListButtons() {
  return (
    <span className="inline-flex overflow-hidden rounded-[5px] border border-border text-[11px] leading-none text-foreground" aria-hidden>
      <span className="px-1.5 py-0.5">−</span>
      <span className="border-l border-border px-1.5 py-0.5">+</span>
    </span>
  );
}

function Step({ n, children, action }: { n: number; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <li className="flex items-center gap-3">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-warning/15 text-[11px] font-medium text-warning">
        {n}
      </span>
      <div className="min-w-0 flex-1 text-xs leading-relaxed text-foreground">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </li>
  );
}

/**
 * The System audio row when macOS lists Vocify as allowed but won't hand the audio over. The steps follow what the
 * last attempt showed: switch it off and on first; still failing after a relaunch, remove and add it again.
 */
export function CallAudioFixRow({
  fix,
  canRelaunch,
  testing,
  onOpenSettings,
  onRelaunch,
  onTest,
}: {
  fix: CallAudioFix;
  canRelaunch: boolean;
  testing: boolean;
  onOpenSettings: () => void;
  onRelaunch: () => void;
  onTest: () => void;
}) {
  const body = fix.relaunched
    ? "Relaunched. Test it to see if macOS hands the audio over now."
    : fix.step === "readd"
      ? "Still not working. macOS needs Vocify added to the list again."
      : "macOS lists Vocify as allowed but isn't giving it the call's audio.";

  return (
    <div className="rounded-2xl border border-warning/40 bg-warning/5 px-4 py-3" role="status" aria-live="polite">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-warning/15 text-warning">
            <AlertCircle className="h-4 w-4" />
          </div>
          <div className="min-w-0 text-left">
            <p className="text-sm font-medium text-foreground">System audio isn't working</p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{body}</p>
          </div>
        </div>
        {fix.relaunched ? (
          <Button type="button" size="sm" variant="outline" className="shrink-0 rounded-full" disabled={testing} onClick={onTest}>
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Test it"}
          </Button>
        ) : null}
      </div>

      <ol className="mt-3 space-y-2.5 pl-11">
        <Step
          n={1}
          action={
            <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={onOpenSettings}>
              Open Settings
            </Button>
          }
        >
          Open Screen &amp; System Audio Recording.
        </Step>
        <Step n={2}>
          {fix.step === "readd" ? (
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <span>
                Select <strong>Vocify</strong>, press − to remove it, then + to add it back:
              </span>
              <MiniListButtons />
            </span>
          ) : (
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <span>
                Turn <strong>Vocify</strong> off, then on again:
              </span>
              <MiniSwitch on={true} />
              <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden />
              <MiniSwitch on={false} />
              <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden />
              <MiniSwitch on={true} />
            </span>
          )}
        </Step>
        <Step
          n={3}
          action={
            canRelaunch ? (
              <Button type="button" size="sm" variant="outline" className="rounded-full" onClick={onRelaunch}>
                Relaunch
              </Button>
            ) : undefined
          }
        >
          {canRelaunch ? "Relaunch Vocify. macOS applies it only after a restart." : "Quit Vocify (⌘Q) and open it again."}
        </Step>
      </ol>
    </div>
  );
}
