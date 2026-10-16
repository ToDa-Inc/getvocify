import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The reader is this close to the end: new content keeps them at the end (Ayuda). */
const FOLLOW_SLACK_PX = 80;
const FADE_PX = 14;

/**
 * A list that scrolls inside its own block, with a soft fade at an edge only while there is more in that direction.
 * `follow`: stays at the end while the reader is near it and lets go when they scroll up; its position is kept when the
 * pane is hidden (the panes stay mounted).
 */
export function FollowScroll({ children, follow = false, className }: { children: ReactNode; follow?: boolean; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const near = useRef(true);
  const [edge, setEdge] = useState({ top: false, bottom: false });

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const left = el.scrollHeight - el.scrollTop - el.clientHeight;
    near.current = left <= FOLLOW_SLACK_PX;
    setEdge((e) => (e.top === el.scrollTop > 1 && e.bottom === left > 1 ? e : { top: el.scrollTop > 1, bottom: left > 1 }));
  }, []);

  // After every render: new content may have changed what is below.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (follow && near.current && el.scrollHeight > el.clientHeight) {
      el.scrollTo({ top: el.scrollHeight, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
    measure();
  });

  const mask = `linear-gradient(to bottom, ${edge.top ? `transparent 0, black ${FADE_PX}px` : "black 0"}, ${
    edge.bottom ? `black calc(100% - ${FADE_PX}px), transparent 100%` : "black 100%"
  })`;
  return (
    <div
      ref={ref}
      onScroll={measure}
      style={{ maskImage: mask, WebkitMaskImage: mask }}
      className={cn("h-full overflow-y-auto overscroll-contain [scrollbar-width:thin]", className)}
    >
      {children}
    </div>
  );
}
