import { useEffect, useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Text you click to edit: no border and no box at rest or on hover (the text cursor says it can
 * be typed into), a faint tint only while typing. A playbook reads as a document, never a form.
 */
export const inlineField =
  "block w-full cursor-text rounded-md bg-transparent px-1.5 -mx-1.5 text-foreground outline-none transition-colors " +
  "placeholder:text-muted-foreground/60 focus:bg-secondary/50 " +
  "aria-[invalid=true]:bg-destructive/5 aria-[invalid=true]:ring-1 aria-[invalid=true]:ring-destructive/30";

function fit(node: HTMLTextAreaElement) {
  node.style.height = "auto";
  node.style.height = `${node.scrollHeight}px`;
}

/**
 * A one-line-at-rest textarea that grows with its content (criteria and answers wrap). It
 * refits when its width changes too (a resized window, a tab shown), or a field measured
 * narrow keeps a tall empty box.
 */
export function InlineTextarea({ className, value, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (ref.current) fit(ref.current);
  }, [value]);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    let width = node.clientWidth;
    const observer = new ResizeObserver(() => {
      if (node.clientWidth === width) return;
      width = node.clientWidth;
      fit(node);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      className={cn(inlineField, "resize-none overflow-hidden leading-relaxed", className)}
      {...rest}
    />
  );
}
