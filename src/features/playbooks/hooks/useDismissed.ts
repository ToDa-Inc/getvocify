import { useCallback, useState } from "react";
import { addDismissed, parseDismissed, removeDismissed } from "@/lib/dismissed-keys";

const PREFIX = "vocify:dismissed:";

function stored(scope: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + scope);
  } catch {
    return null; // storage blocked
  }
}

/**
 * Suggestions a manager dismissed ("Descartar"), remembered in this browser so they don't come
 * back on every visit. A convenience, not data: losing it only shows the suggestion again.
 * Every change starts from what is stored, so several components sharing a scope don't undo each other.
 */
export function useDismissed(scope: string) {
  const [keys, setKeys] = useState<Set<string>>(() => parseDismissed(stored(scope)));
  const update = useCallback(
    (change: (raw: string | null, key: string) => Set<string>, key: string) =>
      setKeys((current) => {
        // With storage blocked there is nothing stored to start from: use this component's own copy.
        const next = change(stored(scope) ?? JSON.stringify([...current]), key);
        try {
          window.localStorage.setItem(PREFIX + scope, JSON.stringify([...next]));
        } catch {
          // Private window or storage blocked: dismissed for this visit only.
        }
        return next;
      }),
    [scope],
  );
  const add = useCallback((key: string) => update(addDismissed, key), [update]);
  const remove = useCallback((key: string) => update(removeDismissed, key), [update]);
  return { keys, has: (key: string) => keys.has(key), add, remove };
}
