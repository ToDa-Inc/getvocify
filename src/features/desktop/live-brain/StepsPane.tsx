import { useEffect, useRef } from "react";
import { Check, Flag, MessageCircleQuestion } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DataChip, StepRow, StepsView } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveCopy } from "./copy";

type Kind = "step" | "data" | "goal";

/** The circle in front of a step: empty, a flag for the goal, beige with a check once done (it pops in when it ticks). */
function Node({ row }: { row: StepRow }) {
  if (row.state === "done") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-beige text-cream animate-in zoom-in-50 fade-in duration-300 motion-reduce:animate-none">
        <Check className="h-2.5 w-2.5" strokeWidth={3} />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors duration-150 motion-reduce:transition-none",
        "group-hover/node:border-beige group-hover/node:bg-beige/15",
        row.state === "current" ? "border-beige" : "border-muted-foreground/40",
        row.kind === "goal" && "border-dashed border-beige",
      )}
    >
      {row.kind === "goal" ? <Flag className="h-2 w-2 text-beige" strokeWidth={1.5} /> : null}
    </span>
  );
}

/** The circle is the tick: by hand it marks a step done, or takes back a mark. Its tooltip says which. */
function Tick({ row, copy, onTick, onUntick }: { row: StepRow; copy: LiveCopy; onTick: () => void; onUntick: () => void }) {
  const done = row.state === "done";
  const label = done ? `${copy.unmark}: ${row.label}` : `${copy.markDone}: ${row.label}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={done ? onUntick : onTick}
          aria-label={label}
          className="group/node -m-1 flex shrink-0 items-center justify-center rounded-full p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          <Node row={row} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{done ? copy.unmark : copy.markDone}</TooltipContent>
    </Tooltip>
  );
}

/** A step that is done or still to come: one line. Hover says what it asks, or the words that ticked it. */
function StepLine({ row, copy, onTick, onUntick }: { row: StepRow; copy: LiveCopy; onTick: () => void; onUntick: () => void }) {
  const done = row.state === "done";
  const tip = done ? (row.by === "rep" ? copy.markedByYou : row.quote ? `«${row.quote}»` : null) : row.concept;
  const name = (
    <span
      tabIndex={tip ? 0 : undefined}
      className={cn(
        "min-w-0 flex-1 truncate rounded text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60",
        done ? "text-muted-foreground/70" : "text-muted-foreground",
      )}
    >
      {row.label}
    </span>
  );
  return (
    <div className="flex min-h-[30px] items-center gap-2.5 px-3.5">
      <Tick row={row} copy={copy} onTick={onTick} onUntick={onUntick} />
      {tip ? (
        <Tooltip>
          <TooltipTrigger asChild>{name}</TooltipTrigger>
          <TooltipContent side="top" className="max-w-[280px]">{tip}</TooltipContent>
        </Tooltip>
      ) : (
        name
      )}
    </div>
  );
}

/** The step that matters now: open and bright. What it asks, its parts as they are heard, and the brain's question from
 * this call when it has one. */
function CurrentStep({
  row,
  suggestion,
  copy,
  onTick,
  onUntick,
}: {
  row: StepRow;
  suggestion: string | null;
  copy: LiveCopy;
  onTick: () => void;
  onUntick: () => void;
}) {
  return (
    <div data-current className="mx-2 my-1 space-y-2 rounded-xl bg-beige/10 px-3 py-2.5 ring-1 ring-beige/25 animate-in fade-in duration-200 motion-reduce:animate-none">
      <div className="flex items-start gap-2.5">
        <span className="mt-px">
          <Tick row={row} copy={copy} onTick={onTick} onUntick={onUntick} />
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-[14px] font-semibold leading-snug text-foreground">{row.label}</p>
          {row.concept ? <p className="text-[12.5px] leading-snug text-muted-foreground">{row.concept}</p> : null}
        </div>
      </div>
      {row.parts.length ? (
        <div className="space-y-1 pl-[26px]">
          <div className="flex flex-wrap gap-1">
            {row.parts.map((part) => (
              <span
                key={part.id}
                className={cn(
                  "inline-flex h-6 items-center gap-1 rounded-full px-2 text-[12px] transition-colors duration-200 motion-reduce:transition-none",
                  part.done ? "bg-beige/15 text-foreground" : "text-muted-foreground ring-1 ring-inset ring-border",
                )}
              >
                {part.done ? <Check className="h-3 w-3 text-beige animate-in zoom-in-50 duration-300 motion-reduce:animate-none" strokeWidth={2} /> : null}
                {part.label}
              </span>
            ))}
          </div>
          {row.need !== null && row.need < row.parts.length ? (
            <p className="text-[11.5px] text-muted-foreground">{copy.compact.enough(row.need, row.parts.length)}</p>
          ) : null}
        </div>
      ) : null}
      {suggestion ? <Suggestion text={suggestion} copy={copy} /> : null}
    </div>
  );
}

function Suggestion({ text, copy, className = "pl-[26px]" }: { text: string; copy: LiveCopy; className?: string }) {
  return (
    <div className={cn("flex items-start gap-2", className)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} aria-label={copy.compact.suggestionTip} className="mt-[3px] shrink-0 rounded text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60">
            <MessageCircleQuestion className="h-3.5 w-3.5" strokeWidth={1.5} />
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[260px]">{copy.compact.suggestionTip}</TooltipContent>
      </Tooltip>
      <p className="select-text text-[13px] leading-snug text-foreground/85">{text}</p>
    </div>
  );
}

/** What to find out: a chip each, ticked as they say it. The chip is the tick; hover shows what they said or a good answer. */
function Chip({ chip, copy, onTick, onUntick }: { chip: DataChip; copy: LiveCopy; onTick: () => void; onUntick: () => void }) {
  const done = chip.state === "done";
  const tip = done && chip.by === "rep" ? copy.markedByYou : chip.detail;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={done ? onUntick : onTick}
          aria-pressed={done}
          aria-label={`${done ? copy.unmark : copy.markDone}: ${chip.label}`}
          className={cn(
            "inline-flex h-6 max-w-full items-center gap-1 rounded-full px-2 text-[12px] transition-colors duration-200 motion-reduce:transition-none",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60",
            done && "bg-beige/15 text-foreground hover:bg-beige/20",
            chip.state === "current" && "text-foreground ring-1 ring-inset ring-beige/60 hover:bg-beige/10",
            chip.state === "pending" && "text-muted-foreground ring-1 ring-inset ring-border hover:text-foreground",
          )}
        >
          {done ? <Check className="h-3 w-3 shrink-0 text-beige animate-in zoom-in-50 duration-300 motion-reduce:animate-none" strokeWidth={2} /> : null}
          <span className="truncate">{chip.label}</span>
        </button>
      </TooltipTrigger>
      {tip ? <TooltipContent side="top" className="max-w-[260px]">{tip}</TooltipContent> : null}
    </Tooltip>
  );
}

/**
 * Pasos, the compact window's main tab: the playbook's steps in order, ticking themselves as the call covers them. Only the
 * step that matters now is open; the others are one line. What to find out sits under them as chips.
 */
export function StepsPane({
  view,
  copy,
  helpOn,
  typeName,
  onTick,
  onUntick,
}: {
  view: StepsView;
  copy: LiveCopy;
  helpOn: boolean;
  typeName: string | null;
  onTick: (id: string, kind: Kind) => void;
  onUntick: (id: string, kind: Kind) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const current = view.rows.find((row) => row.state === "current")?.id ?? view.data.find((chip) => chip.state === "current")?.id ?? null;

  // The current step stays in view when it moves on. The list scrolls itself: scrollIntoView would move the window too.
  useEffect(() => {
    const box = ref.current;
    const card = box?.querySelector<HTMLElement>("[data-current]");
    if (!box || !card) return;
    const top = card.offsetTop - box.offsetTop;
    if (top < box.scrollTop || top + card.offsetHeight > box.scrollTop + box.clientHeight) {
      box.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
    }
  }, [current]);

  if (!helpOn) return <p className="px-6 pt-8 text-center text-[13px] text-muted-foreground">{copy.off}</p>;
  if (!view.hasPlaybook) {
    return (
      <div className="p-3.5">
        <div className="rounded-xl bg-secondary/50 px-3.5 py-3">
          <p className="text-[13px] font-medium text-foreground">{typeName ? copy.noPlaybook(typeName) : copy.noType}</p>
          <p className="text-[12px] text-muted-foreground">{copy.noPlaybookBody}</p>
        </div>
      </div>
    );
  }

  const currentChip = view.data.find((chip) => chip.state === "current");
  return (
    <div ref={ref} className="relative h-full overflow-y-auto py-2">
      {view.rows.length ? (
        view.rows.map((row) =>
          row.state === "current" ? (
            <CurrentStep
              key={row.id}
              row={row}
              suggestion={view.suggestion}
              copy={copy}
              onTick={() => onTick(row.id, row.kind)}
              onUntick={() => onUntick(row.id, row.kind)}
            />
          ) : (
            <StepLine key={row.id} row={row} copy={copy} onTick={() => onTick(row.id, row.kind)} onUntick={() => onUntick(row.id, row.kind)} />
          ),
        )
      ) : (
        <p className="px-3.5 py-2 text-[12px] text-muted-foreground">{copy.compact.noSteps}</p>
      )}

      {view.data.length ? (
        <div {...(currentChip ? { "data-current": true } : {})} className="mt-3 space-y-1.5 px-3.5 pb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{copy.compact.toFind}</p>
          <div className="flex flex-wrap gap-1">
            {view.data.map((chip) => (
              <Chip key={chip.id} chip={chip} copy={copy} onTick={() => onTick(chip.id, "data")} onUntick={() => onUntick(chip.id, "data")} />
            ))}
          </div>
          {currentChip && view.suggestion ? (
            <Suggestion text={view.suggestion} copy={copy} className="pt-1" />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
