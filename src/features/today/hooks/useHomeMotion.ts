import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { dropLeaving, retainLeaving, type Leaving } from "@shared/ui/today-card.js";

const LEAVE_MS = 150;

/** Keeps resolved rows in place while they fade out, then drops them. */
export function useHomeLeaving<T>(entries: T[], keyOf: (entry: T) => string) {
  const prev = useRef<Leaving<T>[]>([]);
  const [rows, setRows] = useState<Leaving<T>[]>(() => entries.map((entry) => ({ entry, leaving: false })));

  useEffect(() => {
    const next = retainLeaving(prev.current, entries, keyOf);
    prev.current = next;
    setRows(next);
    const timers = next
      .filter((row) => row.leaving)
      .map((row) =>
        window.setTimeout(() => {
          setRows((current) => {
            const dropped = dropLeaving(current, keyOf(row.entry), keyOf);
            prev.current = dropped;
            return dropped;
          });
        }, LEAVE_MS),
      );
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [entries, keyOf]);

  return useMemo(() => rows, [rows]);
}

export const useLeaving = useHomeLeaving;

/** Collapse a card to its measured height when it settles. */
export function useMeasuredSwap(ref: RefObject<HTMLElement | null>, token: string) {
  useEffect(() => {
    const node = ref.current;
    if (!node || token !== "settled") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const height = node.getBoundingClientRect().height;
    node.style.height = `${height}px`;
    node.style.overflow = "hidden";
    requestAnimationFrame(() => {
      node.style.transition = "height 150ms ease, opacity 150ms ease";
      node.style.height = "0px";
      node.style.opacity = "0";
    });
  }, [ref, token]);
}
