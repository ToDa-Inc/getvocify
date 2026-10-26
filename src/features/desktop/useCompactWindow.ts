import { useCallback, useEffect, useState } from "react";
import { getDesktopBridge } from "@/lib/desktop-host";

/**
 * The dashboard window's compact mode (desktop app only): whether it is compact, and the way to change it. `available` is
 * false outside the desktop app and in builds without it; the window itself says when it changed, so every view agrees.
 */
export function useCompactWindow() {
  const bridge = getDesktopBridge()?.window;
  const [compact, setCompactState] = useState(false);

  useEffect(() => {
    if (!bridge) return;
    let alive = true;
    void bridge.get().then((state) => {
      if (alive) setCompactState(Boolean(state?.compact));
    }).catch(() => undefined);
    const off = bridge.onCompact((state) => setCompactState(Boolean(state?.compact)));
    return () => {
      alive = false;
      off();
    };
  }, [bridge]);

  const setCompact = useCallback(
    (on: boolean) => {
      if (!bridge) return;
      void bridge.setCompact(on).then((state) => setCompactState(Boolean(state?.compact))).catch(() => undefined);
    },
    [bridge],
  );

  return { available: Boolean(bridge), compact, setCompact };
}
