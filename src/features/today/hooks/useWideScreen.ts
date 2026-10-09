import { useCallback, useSyncExternalStore } from "react";
import { HOME_WIDE_PX } from "@shared/ui/home.js";

/** True while the rep home's right column is on screen (the `xl` breakpoint). */
export function useWideScreen() {
  const subscribe = useCallback((onStore: () => void) => {
    const mq = window.matchMedia(`(min-width: ${HOME_WIDE_PX}px)`);
    mq.addEventListener("change", onStore);
    return () => mq.removeEventListener("change", onStore);
  }, []);
  const getSnapshot = useCallback(
    () => window.matchMedia(`(min-width: ${HOME_WIDE_PX}px)`).matches,
    [],
  );
  const getServerSnapshot = useCallback(() => true, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
