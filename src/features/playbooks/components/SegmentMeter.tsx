import { cn } from "@/lib/utils";

export type SegmentTone = "success" | "warning" | "muted" | "current" | "pending";

const TONE: Record<SegmentTone, string> = {
  success: "bg-success/70",
  warning: "bg-warning/80",
  muted: "bg-muted-foreground/40",
  current: "bg-beige",
  pending: "bg-secondary",
};

/**
 * Progress as one segment per step (Coaching's step meter): green done, amber changed, grey left aside, beige the one
 * on screen, pale the ones to come. Colour only where it means something.
 */
export function SegmentMeter({ segments, label, className }: { segments: SegmentTone[]; label: string; className?: string }) {
  return (
    <span className={cn("flex w-24 gap-0.5", className)} role="img" aria-label={label}>
      {segments.map((tone, index) => (
        <span key={index} className={cn("h-1.5 flex-1 rounded-full transition-colors duration-200", TONE[tone])} />
      ))}
    </span>
  );
}
