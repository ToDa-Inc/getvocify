import { useState } from "react";
import { Check, ChevronDown, Flag } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { FaltaItem, HechoItem, ProgressView } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveCopy } from "./copy";
import { Collapse } from "./PointCard";
import { FollowScroll } from "./FollowScroll";

const VISIBLE = 3;

/** The beige card with the one thing that matters now. Also the peek behind Preguntar. */
export function AhoraCard({
  now,
  copy,
  onTick,
  pulse = false,
  clearOfClose = false,
}: {
  now: NonNullable<ProgressView["now"]>;
  copy: LiveCopy;
  onTick: () => void;
  pulse?: boolean;
  /** In the peek: its tick keeps clear of the close button. */
  clearOfClose?: boolean;
}) {
  return (
    <div
      data-now={now.id}
      className={cn(
        "space-y-1.5 rounded-xl bg-beige/10 px-3.5 py-3 ring-1 ring-beige/25 transition-shadow duration-700",
        "animate-in fade-in slide-in-from-bottom-1 duration-200 motion-reduce:animate-none",
        pulse && "ring-2 ring-beige/60",
      )}
    >
      <div className={cn("flex items-baseline gap-2", clearOfClose && "pr-6")}>
        <span className="shrink-0 text-[11px] font-semibold text-beige">{copy.now}</span>
        <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
          {now.kind === "data" ? `${copy.find} · ${now.label}` : now.label}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onTick}
              aria-label={copy.markDone}
              className="flex h-[18px] w-[18px] shrink-0 items-center justify-center self-center rounded-full text-beige transition-colors duration-150 hover:bg-beige/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
            >
              <Check className="h-2.5 w-2.5" strokeWidth={2.5} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{copy.markDone}</TooltipContent>
        </Tooltip>
      </div>
      <p className="select-text text-[15px] font-medium leading-snug text-foreground">«{now.say}»</p>
    </div>
  );
}

function Node({ kind, done = false }: { kind: FaltaItem["kind"]; done?: boolean }) {
  if (done) {
    return (
      <span className="flex h-[13px] w-[13px] shrink-0 items-center justify-center rounded-full bg-beige text-cream">
        <Check className="h-2 w-2" strokeWidth={3} />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "flex h-[13px] w-[13px] shrink-0 items-center justify-center border transition-colors duration-150 motion-reduce:transition-none",
        "border-muted-foreground/40 group-hover/node:border-beige group-hover/node:bg-beige/15",
        kind === "data" ? "rounded-[4px]" : "rounded-full",
        kind === "goal" && "border-dashed border-beige",
      )}
    >
      {kind === "goal" ? <Flag className="h-2 w-2 text-beige" /> : null}
    </span>
  );
}

function FaltaRow({
  item,
  copy,
  open,
  onToggle,
  onTick,
}: {
  item: FaltaItem;
  copy: LiveCopy;
  open: boolean;
  onToggle: () => void;
  onTick: () => void;
}) {
  const name = (
    <span className="min-w-0 flex-1 truncate text-left text-[13px] text-muted-foreground transition-colors duration-150 group-hover/name:text-foreground motion-reduce:transition-none">
      {item.label}
    </span>
  );
  return (
    <div>
      <div className="flex min-h-[26px] items-center gap-2.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onTick}
              aria-label={`${copy.markDone}: ${item.label}`}
              className="group/node -m-1 flex shrink-0 items-center justify-center rounded-full p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
            >
              <Node kind={item.kind} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{copy.markDone}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            {item.ask ? (
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={open}
                className="group/name flex min-w-0 flex-1 items-center gap-1.5 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
              >
                {name}
                <ChevronDown className={cn("h-2 w-2 shrink-0 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} />
              </button>
            ) : (
              <span tabIndex={0} className="group/name flex min-w-0 flex-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60">
                {name}
              </span>
            )}
          </TooltipTrigger>
          {item.tip ? <TooltipContent side="top" className="max-w-xs">{item.tip}</TooltipContent> : null}
        </Tooltip>
      </div>
      {item.ask ? (
        <Collapse open={open}>
          <p className="my-0.5 ml-[23px] select-text rounded-xl bg-secondary/50 px-3 py-2 text-[13px] leading-snug text-foreground">«{item.ask}»</p>
        </Collapse>
      ) : null}
    </div>
  );
}

function HechoRow({ item, copy, onUntick }: { item: HechoItem; copy: LiveCopy; onUntick: () => void }) {
  const detail = item.by === "rep" ? copy.markedByYou : item.detail;
  return (
    <div className="flex min-h-[26px] items-center gap-2.5">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onUntick}
            aria-label={`${copy.unmark}: ${item.label}`}
            className="-m-1 flex shrink-0 items-center justify-center rounded-full p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
          >
            <Node kind={item.kind} done />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">{copy.unmark}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="min-w-0 flex-1 truncate rounded text-[13px] text-muted-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60">
            {item.label}
          </span>
        </TooltipTrigger>
        {item.reread ? <TooltipContent side="top">{copy.reread}</TooltipContent> : null}
      </Tooltip>
      {detail ? <span className="max-w-[45%] shrink-0 truncate text-[12px] text-muted-foreground/70">{detail}</span> : null}
    </div>
  );
}

/** Conversación: where the call is against the playbook. Ahora, Falta, Hecho. */
export function ConversacionPane({
  view,
  copy,
  helpOn,
  typeName,
  pulseNow,
  onTick,
  onUntick,
  offline,
}: {
  view: ProgressView;
  copy: LiveCopy;
  helpOn: boolean;
  typeName: string | null;
  pulseNow: boolean;
  onTick: (id: string, kind: FaltaItem["kind"]) => void;
  onUntick: (id: string, kind: FaltaItem["kind"]) => void;
  offline: React.ReactNode;
}) {
  const [showAll, setShowAll] = useState(false);
  const [hechoOpen, setHechoOpen] = useState(false);
  const [askOpen, setAskOpen] = useState<string | null>(null);

  if (!helpOn) return <p className="px-6 pt-8 text-center text-[13px] text-muted-foreground">{copy.off}</p>;
  if (!view.hasPlaybook) {
    return (
      <FollowScroll>
        <div className="p-3.5">
          {offline}
          <div className="rounded-xl bg-secondary/50 px-3.5 py-3">
            <p className="text-[13px] font-medium text-foreground">{typeName ? copy.noPlaybook(typeName) : copy.noType}</p>
            <p className="text-[12px] text-muted-foreground">{copy.noPlaybookBody}</p>
          </div>
        </div>
      </FollowScroll>
    );
  }

  const shown = showAll ? view.falta : view.falta.slice(0, VISIBLE);
  const hidden = view.falta.length - VISIBLE;
  return (
    <FollowScroll>
      <div key={view.name ?? "playbook"} className="p-3.5 animate-in fade-in duration-200 motion-reduce:animate-none">
        {offline}
        <div className="flex h-[18px] items-center gap-3">
          <span className="shrink-0 text-[13px] font-semibold text-foreground">{view.name ?? copy.playbook}</span>
          <span className="h-[3px] max-w-[160px] flex-1 overflow-hidden rounded-full bg-secondary" aria-hidden>
            <span
              className="block h-full rounded-full bg-beige transition-[width] duration-[400ms] ease-out motion-reduce:transition-none"
              style={{ width: `${view.total ? Math.round((view.done / view.total) * 100) : 0}%` }}
            />
          </span>
          <span className="shrink-0 text-[12px] tabular-nums text-muted-foreground">{copy.progressOf(view.done, view.total)}</span>
        </div>

        {view.now ? (
          <div className="mt-3">
            <AhoraCard now={view.now} copy={copy} pulse={pulseNow} onTick={() => onTick(view.now!.id, view.now!.kind)} />
          </div>
        ) : null}

        {view.falta.length ? (
          <div className="mt-4">
            <p className="pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{copy.missing(view.falta.length)}</p>
            <div className="flex flex-col">
              {shown.map((item) => (
                <FaltaRow
                  key={item.id}
                  item={item}
                  copy={copy}
                  open={askOpen === item.id}
                  onToggle={() => setAskOpen((id) => (id === item.id ? null : item.id))}
                  onTick={() => onTick(item.id, item.kind)}
                />
              ))}
            </div>
            {hidden > 0 ? (
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="ml-[23px] mt-1 text-[12px] text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
              >
                {showAll ? copy.less : copy.more(hidden)}
              </button>
            ) : null}
          </div>
        ) : null}

        {view.hecho.length ? (
          <div className="mt-4">
            <button
              type="button"
              onClick={() => setHechoOpen((v) => !v)}
              aria-expanded={hechoOpen}
              className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
            >
              {copy.done(view.hecho.length)}
              <ChevronDown className={cn("h-2 w-2 transition-transform duration-200 motion-reduce:transition-none", hechoOpen && "rotate-180")} />
            </button>
            <Collapse open={hechoOpen}>
              <div className="flex flex-col pt-1">
                {view.hecho.map((item) => (
                  <HechoRow key={item.id} item={item} copy={copy} onUntick={() => onUntick(item.id, item.kind)} />
                ))}
              </div>
            </Collapse>
          </div>
        ) : null}
      </div>
    </FollowScroll>
  );
}
