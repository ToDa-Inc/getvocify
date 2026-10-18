import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/**
 * The one window the Playbook page creates and edits in: a title, one line under it, a body that scrolls, and a footer that
 * stays put. Every screen of a flow is drawn inside it, so moving on never leaves the window.
 */
export function WindowShell({
  open,
  onOpenChange,
  title,
  lead,
  footer,
  wide = false,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  lead?: string;
  footer?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("flex max-h-[88vh] flex-col gap-0 overflow-hidden rounded-2xl border-border/70 bg-background p-0 shadow-xl sm:rounded-2xl", wide ? "max-w-4xl" : "max-w-2xl")}>
        <div className="space-y-1.5 px-6 pb-5 pt-7 md:px-8">
          <DialogTitle className="text-[22px] font-semibold tracking-[-0.015em] text-foreground">{title}</DialogTitle>
          <DialogDescription className={lead ? "text-[15px] leading-relaxed text-muted-foreground" : "sr-only"}>{lead || title}</DialogDescription>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 md:px-8">{children}</div>
        {footer ? <div className="flex items-center justify-between gap-3 border-t border-border/50 px-6 py-4 md:px-8">{footer}</div> : null}
      </DialogContent>
    </Dialog>
  );
}

/** Where the Head of Sales is in a flow of two screens: done, here, next. */
export function StepLine({ steps, at }: { steps: string[]; at: number }) {
  return (
    <ol className="flex items-center gap-2 text-[13px]">
      {steps.map((step, index) => (
        <li key={step} className="flex items-center gap-2">
          <span
            className={cn(
              "flex h-5 w-5 items-center justify-center rounded-full text-[11px] tabular-nums",
              index < at ? "bg-success/15 text-success" : index === at ? "bg-foreground text-background" : "bg-secondary text-muted-foreground",
            )}
          >
            {index < at ? <Check aria-hidden className="h-3 w-3" strokeWidth={2.5} /> : index + 1}
          </span>
          <span className={index === at ? "text-foreground" : "text-muted-foreground"}>{step}</span>
          {index < steps.length - 1 ? <span aria-hidden className="mx-1 hidden h-px w-6 bg-border sm:block" /> : null}
        </li>
      ))}
    </ol>
  );
}
