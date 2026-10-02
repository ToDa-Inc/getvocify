import { useCallback, useState } from "react";

const PREFIX = "vocify:dismissed:";

function read(scope: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(PREFIX + scope);
    const list = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(list) ? list.map(String) : []);
  } catch {
    return new Set();
  }
}

/**
 * Suggestions a manager dismissed ("Descartar"), remembered in this browser so they don't come
 * back on every visit. A convenience, not data: losing it only shows the suggestion again.
 */
export function useDismissed(scope: string) {
  const [keys, setKeys] = useState<Set<string>>(() => read(scope));
  const add = useCallback(
    (key: string) =>
      setKeys((current) => {
        const next = new Set(current).add(key);
        try {
          window.localStorage.setItem(PREFIX + scope, JSON.stringify([...next]));
        } catch {
          // Private window or storage blocked: dismissed for this visit only.
        }
        return next;
      }),
    [scope],
  );
  return { keys, has: (key: string) => keys.has(key), add };
}
