import { useCallback, useEffect, useState } from "react";
import { getDesktopBridge, type DesktopUpdateStatus } from "@/lib/desktop-host";

/**
 * The desktop app's version and self-update, live. `null` when this is not the desktop app, or a build without
 * `updates` (then there is nothing to show).
 */
export function useDesktopUpdates() {
  const updates = getDesktopBridge()?.updates;
  const [status, setStatus] = useState<DesktopUpdateStatus | null>(null);
  // Restart now was refused: a recording (or a call note being saved) is in progress.
  const [mustWait, setMustWait] = useState(false);

  useEffect(() => {
    if (!updates) return;
    let alive = true;
    void updates.status().then((s) => alive && setStatus(s));
    const off = updates.onChanged((s) => setStatus(s));
    return () => {
      alive = false;
      off();
    };
  }, [updates]);

  const check = useCallback(() => {
    if (!updates) return;
    void updates.check().then((s) => s && setStatus(s));
  }, [updates]);

  const install = useCallback(() => {
    if (!updates?.install) return;
    void updates.install().then((restarting) => setMustWait(!restarting));
  }, [updates]);

  return updates ? { status, check, install: updates.install ? install : null, mustWait } : null;
}
