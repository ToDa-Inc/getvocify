import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** Text until focused: no border at rest, the field only shows itself on hover and focus. */
export const inlineField =
  "block w-full rounded-md border border-transparent bg-transparent px-2 py-1 -mx-2 text-foreground " +
  "placeholder:text-muted-foreground/60 hover:border-border/60 focus:border-border focus:bg-background " +
  "focus:outline-none transition-colors aria-[invalid=true]:border-destructive/50";

/** A one-line-at-rest textarea that grows with its content (criteria and answers wrap). */
export function InlineTextarea({ className, value, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, [value]);
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
