import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import { dropLeaving, retainLeaving, settleRowHeights, type Leaving } from "@shared/ui/today-card.js";

const LEAVE_MS = 150;

function clearSettleStyles(node: HTMLElement) {
  node.style.height = "";
  node.style.overflow = "";
  node.style.transition = "";
  node.style.opacity = "";
}

/** Keeps resolved rows in place while they fade out, then drops them. */
export function useLeaving<T>(entries: T[], keyOf: (entry: T) => string) {
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

/** Measure the pending card, then animate down to the settled undo row — never to zero. */
export function useSettleRow(ref: RefObject<HTMLElement | null>, settled: boolean) {
  const pendingHeight = useRef<number | null>(null);
  const wasPending = useRef(true);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (!settled) {
      clearSettleStyles(node);
      pendingHeight.current = node.getBoundingClientRect().height;
      wasPending.current = true;
      return;
    }

    if (!wasPending.current) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const from = pendingHeight.current ?? node.getBoundingClientRect().height;
    const to = node.scrollHeight;
    const plan = settleRowHeights(from, to, reduced);
    wasPending.current = false;

    if (!plan.animate) return;

    node.style.height = `${plan.fromHeight}px`;
    node.style.overflow = "hidden";
    node.getBoundingClientRect();
    node.style.transition = "height 150ms ease";
    node.style.height = `${plan.toHeight}px`;

    const onEnd = (event: TransitionEvent) => {
      if (event.propertyName !== "height") return;
      clearSettleStyles(node);
      node.removeEventListener("transitionend", onEnd);
    };
    node.addEventListener("transitionend", onEnd);
  }, [ref, settled]);
}
