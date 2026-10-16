import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown, Info, X } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { pointSays } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveState } from "./types";
import { pointTag, type LiveCopy } from "./copy";

type Point = LiveState["points"][number];

/** The island's waiting dots. */
export function Dots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)} aria-hidden>
      {[0, 160, 320].map((delay) => (
        <span
          key={delay}
          className="h-1 w-1 rounded-full bg-muted-foreground/60 animate-pulse motion-reduce:animate-none"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

/** A block that folds away (rows 1fr → 0fr) when `open` turns false. */
export function Collapse({ open, children, className }: { open: boolean; children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none",
        open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        className,
      )}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

/** A card that has just ended: it stays one beat, then folds away into Antes. */
export function FoldAway({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setOpen(false));
    return () => cancelAnimationFrame(frame);
  }, []);
  return <Collapse open={open}>{children}</Collapse>;
}

const CARD = "group relative rounded-xl bg-secondary/50 px-3.5 py-3";
const ENTER = "animate-in fade-in slide-in-from-bottom-1 duration-200 motion-reduce:animate-none";

/** Their words, short, in the card's head. */
function Head({ tag, quote, repeated, copy, accent, children }: { tag: string; quote: string; repeated?: boolean; copy: LiveCopy; accent: boolean; children?: ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      {children !== undefined ? children : <span className={cn("shrink-0 text-[11px] font-semibold", accent ? "text-beige" : "text-foreground")}>{tag}</span>}
      {repeated ? <span className="shrink-0 text-[11px] text-muted-foreground">· {copy.repeats}</span> : null}
      <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">{quote}</span>
    </div>
  );
}

/** A point: the tag and their words (small), what to say (the only large text), the source one click away on the tag. */
export function PointCard({
  point,
  copy,
  pulse = false,
  enter = true,
  onDismiss,
  hideDismiss = false,
}: {
  point: Point;
  copy: LiveCopy;
  pulse?: boolean;
  enter?: boolean;
  onDismiss?: () => void;
  hideDismiss?: boolean;
}) {
  const [showSource, setShowSource] = useState(false);
  const says = pointSays(point);
  const noFact = !point.answer && Boolean(point.fallback);
  const tag = pointTag(copy, point);
  const source = point.source?.label ?? null;
  return (
    <div
      data-point={point.id}
      tabIndex={-1}
      className={cn(CARD, "space-y-1.5 transition-shadow duration-700", enter && ENTER, pulse && "ring-2 ring-beige/50")}
    >
      <Head tag={tag} quote={point.title} repeated={point.repeated} copy={copy} accent={point.kind !== "question"}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-expanded={showSource}
              onClick={() => setShowSource((v) => !v)}
              className={cn(
                "shrink-0 rounded text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60",
                point.kind === "question" ? "text-foreground" : "text-beige",
              )}
            >
              {tag}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{source ? copy.sourceOf(source) : noFact ? copy.sourceFallback(copy.notInKnowledge) : tag}</TooltipContent>
        </Tooltip>
      </Head>
      {!hideDismiss && onDismiss ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onDismiss}
              aria-label={copy.dismissAria}
              className="absolute right-2 top-2 flex h-[18px] w-[18px] items-center justify-center rounded-full text-muted-foreground opacity-0 transition-opacity duration-150 hover:bg-secondary hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 group-hover:opacity-100 motion-reduce:transition-none"
            >
              <X className="h-3 w-3" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{copy.dismiss}</TooltipContent>
        </Tooltip>
      ) : null}
      {point.decision && point.decision !== "responder" && point.decision_note ? (
        <p className="text-[11px] text-muted-foreground">{point.decision_note}</p>
      ) : null}
      {noFact ? (
        <p className="flex items-center gap-1 text-[11px] text-warning">
          <Info className="h-2.5 w-2.5" />
          {copy.notInKnowledge}
        </p>
      ) : null}
      <p className="select-text text-[15px] font-medium leading-snug text-foreground">{says}</p>
      {showSource && source ? <p className="text-[11px] text-muted-foreground">{copy.sourceOf(source)}</p> : null}
    </div>
  );
}

/** A point the model is still writing: what they said, "Leyendo…" until its first words, then the words with a caret. */
export function DraftCard({ title, say, copy, enter = true }: { title: string | null; say: string | null; copy: LiveCopy; enter?: boolean }) {
  return (
    <div className={cn(CARD, "space-y-1.5", enter && ENTER)} aria-live="polite">
      <Head tag="" quote={title ?? ""} copy={copy} accent={false}>
        {null}
      </Head>
      {say ? (
        <p className="text-[15px] font-medium leading-snug text-foreground">
          {say}
          <span className="ml-0.5 inline-block h-3 w-[1.5px] translate-y-[2px] bg-beige animate-pulse motion-reduce:animate-none" aria-hidden />
        </p>
      ) : (
        <p className="flex h-[17px] items-center gap-2 text-[12px] text-muted-foreground">
          {copy.reading}
          <Dots />
        </p>
      )}
    </div>
  );
}

/** An open point past the newest two: one line; a click opens it in full. */
export function PointLine({ point, copy, onOpen }: { point: Point; copy: LiveCopy; onOpen: () => void }) {
  const tag = pointTag(copy, point);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onOpen}
          className="flex h-[26px] w-full items-center gap-2 rounded-xl bg-secondary/30 px-3 text-left transition-colors duration-150 hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
        >
          <span className={cn("shrink-0 text-[11px] font-semibold", point.kind === "question" ? "text-foreground" : "text-beige")}>{tag}</span>
          <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">{point.title}</span>
          <ChevronDown className="h-2 w-2 shrink-0 text-muted-foreground" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{copy.open}</TooltipContent>
    </Tooltip>
  );
}
