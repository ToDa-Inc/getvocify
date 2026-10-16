import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const bubble = THEME_TOKENS.radius.control;

/** What a customer (or anyone) said, quoted: the quiet bubble Coaching uses for what was said in a call. */
export function QuoteBubble({ children, label, className }: { children: ReactNode; label?: string; className?: string }) {
  return (
    <div className={cn("space-y-1", className)}>
      {label ? <p className="text-xs font-medium text-muted-foreground">{label}</p> : null}
      <blockquote className={cn(bubble, "bg-secondary/70 px-4 py-3 text-[14.5px] italic leading-relaxed text-foreground/85")}>
        «{children}»
      </blockquote>
    </div>
  );
}

/** Words that would be shown to a salesperson, as the live card shows them: one plain, tinted block. */
export function CardBubble({ children, label, className }: { children: ReactNode; label?: string; className?: string }) {
  return (
    <div className={cn("space-y-1", className)}>
      {label ? <p className="text-xs font-medium text-muted-foreground">{label}</p> : null}
      <div className={cn(bubble, "bg-beige/10 px-4 py-3 text-[15px] leading-relaxed text-foreground")}>{children}</div>
    </div>
  );
}

/** Something was kept: the green block of Coaching's "next time", with an action to take it back. */
export function SavedBubble({ title, children, action, className }: { title: string; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={cn("flex items-start gap-2.5", bubble, "bg-success/10 px-4 py-3", THEME_TOKENS.motion.fadeIn, className)}>
      <Check aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{title}</p>
        <p className="break-words text-[14.5px] leading-relaxed text-foreground">{children}</p>
      </div>
      {action}
    </div>
  );
}
