import { useEffect, useState } from "react";

export type VAction = { action: string; value: string | null; element: HTMLElement };

/** Shared custom element in React: data in as a property, v-action out as a callback.
 *  Returns a callback ref. The element is held in state, not in useRef, so both effects
 *  re-run when it mounts. */
export function useVElement<T>(data: T, onAction?: (detail: VAction) => void) {
  const [element, setElement] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (element) (element as HTMLElement & { data?: T }).data = data;
  }, [element, data]);

  useEffect(() => {
    if (!element || !onAction) return;
    const handler = (event: Event) => onAction((event as CustomEvent<VAction>).detail);
    element.addEventListener("v-action", handler);
    return () => element.removeEventListener("v-action", handler);
  }, [element, onAction]);

  return setElement;
}
