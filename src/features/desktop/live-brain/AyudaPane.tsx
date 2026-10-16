import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { pointSays, pointsView } from "@/lib/live-brain";
import { cn } from "@/lib/utils";
import type { LiveBrain } from "../assist/useLiveBrain";
import type { LivePoint } from "./types";
import { pointTag, type LiveCopy } from "./copy";
import { Collapse, DraftCard, FoldAway, PointCard, PointLine } from "./PointCard";
import { FollowScroll } from "./FollowScroll";

const OUTCOME_TONE: Record<string, string> = {
  answered: "text-beige",
  promised: "text-foreground",
  unanswered: "text-warning",
  gone: "text-muted-foreground",
  dismissed: "text-muted-foreground",
};
/** How long a card that has just ended stays before it folds into Antes (the fold takes about this long). */
const CLOSING_MS = 420;

/** Ayuda: what the other side said that needs handling. Antes (collapsed) first, then the open points, oldest to newest. */
export function AyudaPane({
  brain,
  copy,
  helpOn,
  pulseId,
  expanded,
  onExpand,
  offline,
}: {
  brain: LiveBrain;
  copy: LiveCopy;
  helpOn: boolean;
  pulseId: string | null;
  expanded: ReadonlySet<string>;
  onExpand: (id: string) => void;
  offline: React.ReactNode;
}) {
  const [anteOpen, setAnteOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const view = pointsView(brain.state.points, expanded);
  const [closing, setClosing] = useState<string[]>([]);
  const lastOpen = useRef<string[]>([]);
  const openIds = view.open.map((p: LivePoint) => p.id);
  const openKey = openIds.join("|");
  useEffect(() => {
    const ended = lastOpen.current.filter((id) => !openIds.includes(id) && brain.state.points.some((p: LivePoint) => p.id === id));
    lastOpen.current = openIds;
    if (!ended.length) return;
    setClosing((c) => [...c, ...ended]);
    const timer = window.setTimeout(() => setClosing((c) => c.filter((id) => !ended.includes(id))), CLOSING_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openKey]);

  useEffect(() => {
    if (!pulseId) return;
    root.current?.querySelector(`[data-point="${pulseId}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [pulseId]);

  if (!helpOn) return <p className="px-6 pt-8 text-center text-[13px] text-muted-foreground">{copy.off}</p>;

  const before = view.before.filter((p: LivePoint) => !closing.includes(p.id));
  const ended = closing.map((id) => brain.state.points.find((p: LivePoint) => p.id === id)).filter(Boolean);
  const empty = !view.open.length && !before.length && !ended.length && !brain.drafts.length;

  return (
    <FollowScroll follow>
      <div ref={root} className="flex flex-col gap-2 p-3.5">
        {offline}
        {before.length ? (
          <div>
            <button
              type="button"
              onClick={() => setAnteOpen((v) => !v)}
              aria-expanded={anteOpen}
              className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
            >
              {copy.before(before.length)}
              {view.unanswered ? <span className="font-normal normal-case tracking-normal text-warning">{copy.unanswered(view.unanswered)}</span> : null}
              <ChevronDown className={cn("h-2 w-2 transition-transform duration-200 motion-reduce:transition-none", anteOpen && "rotate-180")} />
            </button>
            <Collapse open={anteOpen}>
              <div className="flex flex-col gap-1 pt-1.5">
                {before.map((point: LivePoint) => (
                  <Tooltip key={point.id}>
                    <TooltipTrigger asChild>
                      <div tabIndex={0} className="flex items-baseline gap-2 rounded text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60">
                        <span className="shrink-0 font-semibold text-foreground">{pointTag(copy, point)}</span>
                        <span className="min-w-0 flex-1 truncate text-muted-foreground">{point.title}</span>
                        <span className={cn("shrink-0 font-medium", OUTCOME_TONE[point.outcome])}>{copy.outcomes[point.outcome]}</span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      {pointSays(point) || point.title}
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </Collapse>
          </div>
        ) : null}

        {view.open.map((point: LivePoint) =>
          view.full.has(point.id) ? (
            <PointCard
              key={point.id}
              point={point}
              copy={copy}
              pulse={pulseId === point.id}
              enter={!brain.fromDraft.includes(point.id)}
              onDismiss={() => brain.dismiss(point.id)}
            />
          ) : (
            <PointLine key={point.id} point={point} copy={copy} onOpen={() => onExpand(point.id)} />
          ),
        )}
        {ended.map((point: LivePoint) => (
          <FoldAway key={`ended-${point.id}`}>
            <PointCard point={point} copy={copy} enter={false} hideDismiss />
          </FoldAway>
        ))}
        {brain.drafts.map((draft, index) => (
          <DraftCard key={`draft-${index}`} title={draft.title} say={draft.say} copy={copy} />
        ))}

        {empty ? <p className="px-4 pt-8 text-center text-[13px] text-muted-foreground">{copy.emptyHelp}</p> : null}
      </div>
    </FollowScroll>
  );
}
