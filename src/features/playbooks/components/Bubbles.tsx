import type { ReactNode } from "react";
import { Check, Lightbulb } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const bubble = THEME_TOKENS.radius.control;

export type Speaker = "client" | "rep" | "unknown";

const TURN: Record<Speaker, string> = {
  client: "rounded-bl-md bg-secondary/70",
  rep: "rounded-br-md bg-foreground/[0.06]",
  unknown: "rounded-bl-md border border-dashed border-border",
};

/** One turn of what was said, the way Coaching's chat reads: the client on the left in grey, the rep on the right.
 * Who speaks shows by side and colour, never by a caption over it: `label` is read by screen readers only. */
export function TurnBubble({ who = "client", label, children, className }: { who?: Speaker; label?: string; children: ReactNode; className?: string }) {
  const right = who === "rep";
  return (
    <div className={cn("flex flex-col", right ? "items-end" : "items-start", className)}>
      {label ? <span className="sr-only">{label}</span> : null}
      <div className={cn("max-w-[94%] rounded-2xl px-3.5 py-2 text-[14.5px] leading-snug text-foreground", TURN[who])}>{children}</div>
    </div>
  );
}

/** The line to say, on the rep's side: green with a bulb, as Coaching shows it. `muted` is the dashed bubble for
 * "nothing to say here". `label` is read by screen readers only. */
export function SayBubble({ label, muted = false, children, className }: { label?: string; muted?: boolean; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-end", className)}>
      {label ? <span className="sr-only">{label}</span> : null}
      <div
        className={cn(
          "max-w-[94%] rounded-2xl rounded-br-md px-3.5 py-2 text-[14.5px] leading-snug",
          muted ? "border border-dashed border-border text-muted-foreground" : "border border-success/25 bg-success/10 text-foreground",
        )}
      >
        {muted ? (
          children
        ) : (
          <span className="flex items-start gap-2">
            <Lightbulb aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} />
            <span className="min-w-0 font-medium">{children}</span>
          </span>
        )}
      </div>
    </div>
  );
}

/** A draft the manager can take, in one plain, tinted block. */
export function CardBubble({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(bubble, "bg-beige/10 px-4 py-3 text-[15px] leading-relaxed text-foreground", className)}>{children}</div>;
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
