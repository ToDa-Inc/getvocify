import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { DesktopPermissionRows } from "./DesktopPermissionsPanel";
import { useDesktopPermissions } from "./useDesktopPermissions";

/** "Later" is remembered per Mac; the Record page panel keeps asking until both are on. */
const DISMISSED_KEY = "vocify.desktop.setupDismissed";
const READY_CLOSE_MS = 1200;

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * First thing the Mac app asks after login: mic and system audio. macOS never prompts for
 * Screen & System Audio Recording on its own, so without this a new user may never see it.
 */
export function DesktopSetupDialog() {
  const permissions = useDesktopPermissions();
  const { available, loading, ready } = permissions;
  const [dismissed, setDismissed] = useState(readDismissed);
  const [open, setOpen] = useState(false);

  // Opens once on launch when something is missing; granting both while it's open closes it.
  useEffect(() => {
    if (!available || loading || dismissed) return;
    if (!ready) setOpen(true);
  }, [available, loading, dismissed, ready]);

  useEffect(() => {
    if (!open || !ready) return;
    const id = window.setTimeout(() => setOpen(false), READY_CLOSE_MS);
    return () => window.clearTimeout(id);
  }, [open, ready]);

  const later = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // Storage blocked: it asks again next launch.
    }
    setDismissed(true);
    setOpen(false);
  };

  if (!available) return null;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : ready ? setOpen(false) : later())}>
      <DialogContent className={`${THEME_TOKENS.radius.container} max-w-lg border-border/70 bg-card p-6 md:p-8`}>
        <div className="text-left">
          <p className={THEME_TOKENS.typography.capsLabel}>Set up this Mac</p>
          <DialogTitle className="text-xl font-semibold tracking-tight text-foreground mt-1">
            {ready ? "You're set" : "Let Vocify hear your calls"}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground mt-1">
            {ready
              ? "Both sides of your next call will be recorded."
              : "Your mic records you. System audio records the other side of Zoom, Meet and Teams."}
          </DialogDescription>
        </div>

        <DesktopPermissionRows permissions={permissions} />

        {ready ? null : (
          <div className="flex justify-end">
            <Button type="button" variant="ghost" size="sm" onClick={later}>
              Do this later
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
