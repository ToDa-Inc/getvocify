import { useEffect, useRef, useState } from "react";
import { Check, History, Info, MessageCircleQuestion, Reply } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { pointSays } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveBrain } from "../assist/useLiveBrain";
import type { LiveCopy } from "./copy";
import { Dots } from "./PointCard";
import type { LivePoint } from "./types";

/** How long Responder's "nothing to answer" stays. */
const NOTHING_MS = 6000;
/** The answer a new one replaces stays as one line this long, then leaves. */
const LEAVE_MS = 2600;
/** «Pensando» waits this long: a reading that ends at once (most are skipped by the backend) never flashes it. */
const THINKING_AFTER_MS = 400;

export type SayKind = "answer" | "unknown" | "explore";
const KIND_ICON: Record<SayKind, typeof Reply> = { answer: Reply, unknown: Info, explore: MessageCircleQuestion };
const KIND_TONE: Record<SayKind, string> = { answer: "text-beige", unknown: "text-warning", explore: "text-muted-foreground" };
export const sayKind = (point: Pick<LivePoint, "kind" | "answer" | "fallback">): SayKind =>
  point.kind === "deepen" ? "explore" : !point.answer && point.fallback ? "unknown" : "answer";
export const quoted = (words: string) => `«${words.replace(/^[«"]|[»"]$/g, "")}»`;

/** The first line of a card: what kind of help it is (always in the same place) and their words. */
export function SayTag({ kind, label }: { kind: SayKind; label: string }) {
  const Icon = KIND_ICON[kind];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold", KIND_TONE[kind])}>
      <Icon className="h-3 w-3" strokeWidth={1.5} />
      {label}
    </span>
  );
}

/** True once `on` has held for `ms`; false at once when it stops. */
function useHeld(on: boolean, ms: number) {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!on) return setHeld(false);
    const timer = window.setTimeout(() => setHeld(true), ms);
    return () => window.clearTimeout(timer);
  }, [on, ms]);
  return held;
}

/**
 * Qué decir, one answer at a time (2026-11-10). The newest open card is whole; the one it replaces shrinks to a line and
 * leaves; the earlier ones open from the icon on the answer's own first line. At the foot, always in the same place, the
 * brain working: the dots and «Pensando» for as long as a reading is really in flight. It promises no text: when the
 * reading ends with nothing, it just stops. The zone is as tall as its one answer and never grows with the call.
 */
export function SaySlot({
  brain,
  copy,
  responder,
  flashId,
  olderOpen,
  onOlder,
}: {
  brain: LiveBrain;
  copy: LiveCopy;
  responder: LiveBrain["asks"]["responder"];
  flashId: string | null;
  olderOpen: boolean;
  onOlder: () => void;
}) {
  const points = brain.state.points as LivePoint[];
  const open = points.filter((point) => point.outcome === "open");
  // The newest open card; the one Responder points at when that is another open one.
  const current = open.find((point) => point.id === flashId) ?? open[open.length - 1] ?? null;
  const draft = current ? null : brain.drafts[0] ?? null;
  const older = points.length - (current ? 1 : 0);
  const thinking = useHeld(brain.reading.points, THINKING_AFTER_MS);

  // The card a new one took the place of: one line for a moment, so the change is seen and nothing jumps.
  const [leaving, setLeaving] = useState<LivePoint | null>(null);
  const last = useRef<LivePoint | null>(null);
  useEffect(() => {
    const before = last.current;
    last.current = current;
    if (!before || !current || before.id === current.id) return;
    setLeaving(before);
    const timer = window.setTimeout(() => setLeaving((point) => (point?.id === before.id ? null : point)), LEAVE_MS);
    return () => window.clearTimeout(timer);
    // Only a new card on screen starts it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  const [nothing, setNothing] = useState<{ seq: number; question: string | null } | null>(null);
  useEffect(() => {
    if (!responder || responder.status !== "nothing") return;
    setNothing({ seq: responder.seq, question: responder.next?.question ?? null });
    const timer = window.setTimeout(() => setNothing((n) => (n?.seq === responder.seq ? null : n)), NOTHING_MS);
    return () => window.clearTimeout(timer);
  }, [responder]);

  const kind = current ? sayKind(current) : "answer";
  const empty = !current && !draft && !nothing && !leaving;
  return (
    <section aria-label={copy.compact.say} className="relative flex max-h-[38%] min-h-[96px] shrink-0 flex-col border-b border-border/60">
      {older > 0 ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onOlder}
              aria-label={copy.compact.older}
              aria-pressed={olderOpen}
              className={cn(
                "absolute right-3.5 top-[15px] z-10 inline-flex h-5 items-center gap-1 rounded-full px-1.5 text-[10.5px] tabular-nums transition-colors duration-150",
                "hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none",
                olderOpen ? "bg-beige/15 text-beige" : "text-muted-foreground/70",
              )}
            >
              <History className="h-3 w-3" strokeWidth={1.5} />
              {older}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">{copy.compact.older}</TooltipContent>
        </Tooltip>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto px-3 pb-1.5 pt-2.5">
        {brain.offlineSince !== null ? <p className="px-0.5 text-[11px] text-warning">{copy.offline}</p> : null}
        {leaving ? (
          <div
            key={leaving.id}
            className="flex min-w-0 shrink-0 items-center gap-1.5 px-3 pr-12 animate-out fade-out fill-mode-forwards motion-reduce:hidden"
            style={{ animationDuration: `${LEAVE_MS}ms` }}
          >
            <Check className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2} />
            <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{pointSays(leaving)}</span>
          </div>
        ) : null}

        {current ? (
          <div
            key={current.id}
            data-point={current.id}
            className={cn(
              "flex shrink-0 flex-col gap-1 rounded-xl px-3 py-2.5 animate-in fade-in slide-in-from-bottom-1 duration-300 motion-reduce:animate-none",
              kind === "explore" ? "ring-1 ring-inset ring-border" : "bg-secondary/60",
              kind === "unknown" && "ring-1 ring-inset ring-warning/40",
              flashId === current.id && "ring-2 ring-beige/50",
            )}
          >
            <div className={cn("flex min-w-0 items-center gap-1.5", older > 0 ? "pr-9" : "pr-1")}>
              <SayTag kind={kind} label={copy.compact.kinds[kind]} />
              {current.title ? <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{quoted(current.title)}</span> : null}
            </div>
            <p className={cn("select-text text-[14px] leading-snug text-foreground", kind === "explore" ? "text-foreground/90" : "font-medium")}>{pointSays(current)}</p>
            <div className="flex items-center gap-2 pt-0.5">
              {current.source?.label ? <span className="min-w-0 truncate text-[11px] text-muted-foreground">{current.source.label}</span> : null}
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => brain.dismiss(current.id)}
                className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[11.5px] text-muted-foreground transition-colors duration-150 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
              >
                <Check className="h-3 w-3" strokeWidth={2} />
                {kind === "explore" ? copy.compact.done.explore : copy.compact.done.answer}
              </button>
            </div>
          </div>
        ) : draft ? (
          // The older brain writes its answer in as it comes.
          <div className="flex shrink-0 flex-col gap-1 rounded-xl bg-secondary/60 px-3 py-2.5">
            <div className={cn("flex min-w-0 items-center gap-1.5", older > 0 ? "pr-9" : "pr-1")}>
              <SayTag kind="answer" label={copy.compact.preparing} />
              {draft.title ? <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{quoted(draft.title)}</span> : null}
            </div>
            {draft.say ? <p className="text-[14px] font-medium leading-snug text-foreground">{draft.say}</p> : <Dots />}
          </div>
        ) : null}

        {nothing ? (
          <div className="flex shrink-0 flex-col gap-0.5 rounded-xl px-3 py-2 ring-1 ring-inset ring-border">
            <p className="text-[11.5px] text-muted-foreground">{brain.cardMode ? copy.compact.nothingNew : copy.nothingFound}</p>
            {nothing.question ? <p className="text-[14px] leading-snug text-foreground/85">{nothing.question}</p> : null}
          </div>
        ) : null}

        {empty && !thinking ? <p className="px-0.5 py-1 text-[12px] text-muted-foreground">{copy.compact.sayEmpty}</p> : null}
      </div>

      {/* Always there, so it never moves the card: empty, or the brain working. */}
      <div className="flex h-6 shrink-0 items-center px-6 pb-1.5" aria-live="polite">
        {thinking ? (
          <div className="flex min-w-0 items-center gap-2 animate-in fade-in duration-200 motion-reduce:animate-none">
            <Dots className="shrink-0" />
            <span className="shrink-0 text-[11.5px] text-muted-foreground">{copy.compact.thinking}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
