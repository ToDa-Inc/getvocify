import { useEffect, useRef, useState } from "react";
import { nextShown } from "@/lib/ask-activity";

/**
 * The text to show for an answer that is still arriving. It glides toward what has been received and keeps
 * gliding after the stream ends, so the last burst does not pop in. Finished answers open in full.
 */
export function useSmoothText(text: string, streaming: boolean): string {
  const shownRef = useRef(streaming ? 0 : text.length);
  const [, paint] = useState(0);
  const target = useRef(text.length);
  const frame = useRef(0);
  target.current = text.length;
  if (shownRef.current > text.length) shownRef.current = text.length; // the answer was rewritten shorter

  useEffect(() => {
    if (shownRef.current >= text.length || frame.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shownRef.current = text.length;
      paint((n) => n + 1);
      return;
    }
    let last = performance.now();
    const tick = (now: number) => {
      shownRef.current = nextShown(shownRef.current, target.current, now - last);
      last = now;
      paint((n) => n + 1);
      frame.current = shownRef.current >= target.current ? 0 : requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }, [text]);

  useEffect(
    () => () => {
      if (frame.current) cancelAnimationFrame(frame.current);
      frame.current = 0;
    },
    [],
  );

  return text.slice(0, shownRef.current);
}
