import { useEffect, useRef, useState } from "react";
import { Check, Flag, MessageCircleQuestion } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DataChip, StepRow, StepsView } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveBrain } from "../assist/useLiveBrain";
import type { LiveCopy } from "./copy";
import { Dots } from "./PointCard";

type Kind = "step" | "data" | "goal";
type Item = { kind: Kind; id: string };
type StepAsk = LiveBrain["asks"]["step"];

/** How long «Apuntado: …» stays beside «Por averiguar». */
const NOTED_MS = 5000;

const same = (a: Item | null, kind: Kind, id: string) => Boolean(a && a.kind === kind && a.id === id);

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

/** The circle is the tick: by hand it marks a step done, or takes back a mark. */
function Tick({ row, copy, onTick, onUntick }: { row: StepRow; copy: LiveCopy; onTick: () => void; onUntick: () => void }) {
  const done = row.state === "done";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={done ? onUntick : onTick}
          aria-label={`${done ? copy.unmark : copy.markDone}: ${row.label}`}
          className="group/node -m-1 flex shrink-0 items-center justify-center rounded-full p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          <Node row={row} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{done ? copy.unmark : copy.markDone}</TooltipContent>
    </Tooltip>
  );
}

/** A question to say, from the call: the icon says it is a suggestion, the words are the rep's to adapt. */
function Question({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-2 text-[13px] leading-snug text-foreground">
      <MessageCircleQuestion className="mt-[2px] h-3.5 w-3.5 shrink-0 text-beige" strokeWidth={1.5} aria-hidden />
      <span className="select-text">{text}</span>
    </p>
  );
}

/** The answer to a tap: "preparing" while the brain writes it from the call, then the question, else a quiet line. */
function Asked({ ask, item, fallback, copy }: { ask: StepAsk; item: Item; fallback: string | null; copy: LiveCopy }) {
  const mine = ask && ask.kind === item.kind && ask.id === item.id ? ask : null;
  if (!mine || mine.status === "reading") {
    return (
      <p className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
        {copy.compact.preparingQuestion}
        <Dots />
      </p>
    );
  }
  const text = mine.question ?? fallback;
  return text ? <Question text={text} /> : <p className="text-[12.5px] text-muted-foreground">{copy.compact.noQuestion}</p>;
}

/** The call's steps as one line: covered, where the call is now, still to come. No number: a "2/6" reads as a score. */
function ProgressLine({ rows }: { rows: StepRow[] }) {
  return (
    <div className="flex items-center gap-1 px-3" aria-hidden>
      {rows.map((row) => (
        <span
          key={`${row.kind}:${row.id}`}
          className={cn(
            "h-1 flex-1 rounded-full transition-colors duration-500 motion-reduce:transition-none",
            row.state === "done" ? "bg-beige" : row.state === "current" ? "bg-beige/45 animate-pulse motion-reduce:animate-none" : "bg-border",
          )}
        />
      ))}
    </div>
  );
}

/** What a step shows when it is open: covered, the words that covered it; else what it asks, its parts as heard, and a
 * question from this call (the brain's own for the step the call is on, or the one the tap asked for). */
function StepBody({ row, suggestion, asked, ask, copy }: { row: StepRow; suggestion: string | null; asked: boolean; ask: StepAsk; copy: LiveCopy }) {
  if (row.state === "done") {
    return <p className="text-[12.5px] leading-snug text-muted-foreground">{row.by === "rep" ? copy.markedByYou : row.quote ? `«${row.quote}»` : copy.markedByYou}</p>;
  }
  return (
    <>
      {row.concept ? <p className="text-[12.5px] leading-snug text-muted-foreground">{row.concept}</p> : null}
      {row.parts.length ? (
        <div className="flex flex-wrap items-center gap-1 pt-0.5">
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
          {row.need !== null && row.need < row.parts.length ? <span className="pl-1 text-[11.5px] text-muted-foreground">{copy.compact.enough(row.need, row.parts.length)}</span> : null}
        </div>
      ) : null}
      {row.kind === "goal" ? null : suggestion ? <Question text={suggestion} /> : asked ? <Asked ask={ask} item={{ kind: row.kind, id: row.id }} fallback={null} copy={copy} /> : null}
    </>
  );
}

/** One step: the circle ticks it, the rest of the row opens it. Every step is an equal row: the one the call is on has a
 * mark («Ahora»), not a box of its own, and a pending step shows a question mark so the row reads as something to press. */
function StepItem({
  row,
  open,
  suggestion,
  asked,
  ask,
  copy,
  onToggle,
  onTick,
  onUntick,
}: {
  row: StepRow;
  open: boolean;
  suggestion: string | null;
  asked: boolean;
  ask: StepAsk;
  copy: LiveCopy;
  onToggle: () => void;
  onTick: () => void;
  onUntick: () => void;
}) {
  const current = row.state === "current";
  const done = row.state === "done";
  return (
    <div
      {...(current ? { "data-current": true } : {})}
      className={cn("group rounded-xl px-3 transition-colors duration-200 motion-reduce:transition-none", open ? "bg-secondary/50 py-2" : "py-1 hover:bg-secondary/60")}
    >
      <div className="flex items-center gap-2.5">
        <Tick row={row} copy={copy} onTick={onTick} onUntick={onUntick} />
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          <span className={cn("min-w-0 truncate text-[13px]", done ? "text-muted-foreground/70" : current || open ? "font-medium text-foreground" : "text-foreground/80")}>{row.label}</span>
          {current ? <span className="inline-flex h-[18px] shrink-0 items-center rounded-full bg-beige/15 px-1.5 text-[10.5px] font-medium text-beige">{copy.compact.now}</span> : null}
          <span className="flex-1" />
          {!done && row.kind !== "goal" ? (
            <span className={cn("inline-flex shrink-0 items-center gap-1 text-[11.5px] transition-colors duration-150 motion-reduce:transition-none", open ? "text-beige" : "text-muted-foreground group-hover:text-beige")}>
              <MessageCircleQuestion className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
              <span className={open ? "" : "hidden group-hover:inline"}>{copy.compact.question}</span>
            </span>
          ) : null}
        </button>
      </div>
      {open ? (
        <div className="flex flex-col gap-1.5 pb-0.5 pl-[26px] pt-1 animate-in fade-in duration-200 motion-reduce:animate-none">
          <StepBody row={row} suggestion={suggestion} asked={asked} ask={ask} copy={copy} />
        </div>
      ) : null}
    </div>
  );
}

/** What to find out: a chip each, ticked as they say it. A tap opens it under the chips: what a good answer is (or what
 * they said), a question for it from the call, and the tick. */
function Chip({ chip, open, onToggle }: { chip: DataChip; open: boolean; onToggle: () => void }) {
  const done = chip.state === "done";
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={cn(
        "inline-flex h-7 max-w-full items-center gap-1.5 rounded-full px-2.5 text-[12.5px] transition-colors duration-200 motion-reduce:transition-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60",
        done ? "bg-beige/15 text-foreground hover:bg-beige/20" : "text-muted-foreground ring-1 ring-inset ring-border hover:text-foreground",
        (open || chip.state === "current") && !done && "text-foreground ring-beige/60",
        open && "ring-1 ring-inset ring-beige/60",
      )}
    >
      {done ? <Check className="h-3 w-3 shrink-0 text-beige animate-in zoom-in-50 duration-300 motion-reduce:animate-none" strokeWidth={2} /> : null}
      <span className="shrink-0">{chip.label}</span>
      {done && chip.detail ? <span className="min-w-0 truncate text-muted-foreground">{chip.detail}</span> : null}
    </button>
  );
}

function ChipBody({
  chip,
  current,
  suggestion,
  asked,
  ask,
  copy,
  onAsk,
  onTick,
  onUntick,
}: {
  chip: DataChip;
  current: boolean;
  suggestion: string | null;
  asked: boolean;
  ask: StepAsk;
  copy: LiveCopy;
  onAsk: () => void;
  onTick: () => void;
  onUntick: () => void;
}) {
  const done = chip.state === "done";
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-secondary/50 px-3 py-2.5 animate-in fade-in duration-200 motion-reduce:animate-none">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[13px] font-semibold text-foreground">{chip.label}</span>
        <button
          type="button"
          onClick={done ? onUntick : onTick}
          className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[12px] text-muted-foreground transition-colors duration-150 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          <Check className="h-3 w-3" strokeWidth={2} />
          {done ? copy.unmark : copy.markDone}
        </button>
      </div>
      {chip.detail ? <p className="text-[12.5px] leading-snug text-muted-foreground">{done ? `«${chip.detail}»` : chip.detail}</p> : done ? <p className="text-[12.5px] text-muted-foreground">{copy.markedByYou}</p> : null}
      {done ? null : asked ? (
        <Asked ask={ask} item={{ kind: "data", id: chip.id }} fallback={chip.question} copy={copy} />
      ) : current && suggestion ? (
        <Question text={suggestion} />
      ) : (
        <button
          type="button"
          onClick={onAsk}
          className="self-start rounded text-[12.5px] font-medium text-beige transition-colors duration-150 hover:text-beige/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          {copy.compact.askThis}
        </button>
      )}
    </div>
  );
}

/**
 * Pasos, the compact window's main tab (2026-11-10): a line of progress, then the playbook's steps as equal rows that tick
 * themselves as the call covers them. No step is forced open: the one the call is on carries «Ahora». A tap on any step or
 * on something to find out opens it in place; a pending one is asked to the brain at once, a question written from what
 * has been said. What they say shows inside its chip. Nothing hides behind a hover.
 */
export function StepsPane({
  view,
  copy,
  helpOn,
  typeName,
  ask,
  onAsk,
  onTick,
  onUntick,
}: {
  view: StepsView;
  copy: LiveCopy;
  helpOn: boolean;
  typeName: string | null;
  ask: StepAsk;
  onAsk: (kind: "step" | "data", id: string) => void;
  onTick: (id: string, kind: Kind) => void;
  onUntick: (id: string, kind: Kind) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [opened, setOpened] = useState<Item | null>(null);
  const [asked, setAsked] = useState<Item | null>(null);
  const current = view.rows.find((row) => row.state === "current") ?? null;
  const currentChip = view.data.find((chip) => chip.state === "current") ?? null;
  const currentKey = current ? `step:${current.id}` : currentChip ? `data:${currentChip.id}` : null;

  // The current step stays in view when it moves on. The list scrolls itself: scrollIntoView would move the window too.
  useEffect(() => {
    const box = ref.current;
    const card = box?.querySelector<HTMLElement>("[data-current]");
    if (!box || !card) return;
    const top = card.offsetTop - box.offsetTop;
    if (top < box.scrollTop || top + card.offsetHeight > box.scrollTop + box.clientHeight) {
      box.scrollTo({ top: Math.max(0, top - 12), behavior: "smooth" });
    }
  }, [currentKey]);

  const askFor = (kind: "step" | "data", id: string) => {
    setAsked({ kind, id });
    onAsk(kind, id);
  };
  // Opening a pending item asks for its question at once: the tap is the ask (the step the call is on already has the
  // brain's own). Closing it keeps nothing.
  const toggle = (kind: "step" | "data" | "goal", id: string, pending: boolean) => {
    if (same(opened, kind, id)) return setOpened(null);
    setOpened({ kind, id });
    const hasOwn = view.suggestion && ((kind === "step" && current?.id === id) || (kind === "data" && currentChip?.id === id));
    if (pending && kind !== "goal" && !hasOwn) askFor(kind, id);
  };

  // What they have just told us: named beside «Por averiguar» for a few seconds when a chip ticks itself.
  const known = useRef<Set<string> | null>(null);
  const [noted, setNoted] = useState<string[]>([]);
  const doneKey = view.data.filter((chip) => chip.state === "done" && chip.by !== "rep").map((chip) => chip.id).join(",");
  useEffect(() => {
    const done = view.data.filter((chip) => chip.state === "done" && chip.by !== "rep");
    const before = known.current;
    known.current = new Set(done.map((chip) => chip.id));
    if (before === null) return;
    const fresh = done.filter((chip) => !before.has(chip.id)).map((chip) => chip.label);
    if (!fresh.length) return;
    setNoted(fresh);
    const timer = window.setTimeout(() => setNoted([]), NOTED_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneKey]);

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

  const openChip = opened?.kind === "data" ? view.data.find((chip) => chip.id === opened.id) ?? null : null;
  const chipShown = openChip;
  return (
    <div ref={ref} className="relative h-full overflow-y-auto px-2.5 pb-4 pt-3">
      {view.rows.length ? <ProgressLine rows={view.rows} /> : null}
      <div className="mt-2.5 flex flex-col gap-0.5">
        {view.rows.length ? (
          view.rows.map((row) => (
            <StepItem
              key={row.id}
              row={row}
              open={same(opened, row.kind, row.id)}
              suggestion={row.state === "current" ? view.suggestion : null}
              asked={same(asked, row.kind, row.id)}
              ask={ask}
              copy={copy}
              onToggle={() => toggle(row.kind, row.id, row.state !== "done")}
              onTick={() => onTick(row.id, row.kind)}
              onUntick={() => onUntick(row.id, row.kind)}
            />
          ))
        ) : (
          <p className="px-3 py-2 text-[12.5px] text-muted-foreground">{copy.compact.noSteps}</p>
        )}
      </div>

      {view.data.length ? (
        <div {...(currentChip && !current ? { "data-current": true } : {})} className="mt-4 space-y-2 px-3">
          <div className="flex h-5 items-center gap-2">
            <p className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{copy.compact.toFind}</p>
            {noted.length ? (
              <span key={noted.join()} className="inline-flex min-w-0 items-center gap-1 text-[11.5px] text-beige animate-in fade-in slide-in-from-left-1 duration-300 motion-reduce:animate-none">
                <Check className="h-3 w-3 shrink-0" strokeWidth={2} />
                <span className="truncate">{copy.compact.noted(noted.join(", "))}</span>
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {view.data.map((chip) => (
              <Chip key={chip.id} chip={chip} open={same(opened, "data", chip.id)} onToggle={() => toggle("data", chip.id, chip.state !== "done")} />
            ))}
          </div>
          {chipShown ? (
            <ChipBody
              key={chipShown.id}
              chip={chipShown}
              current={chipShown.state === "current"}
              suggestion={view.suggestion}
              asked={same(asked, "data", chipShown.id)}
              ask={ask}
              copy={copy}
              onAsk={() => askFor("data", chipShown.id)}
              onTick={() => onTick(chipShown.id, "data")}
              onUntick={() => onUntick(chipShown.id, "data")}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
